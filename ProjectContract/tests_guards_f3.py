# -*- coding: utf-8 -*-
"""F3: characterization-тесты ProjectContract — фиксируют ФАКТ до рефакторинга.

Дисциплина дат (services.compute_own_dates/propagate_dates), идемпотентность
ДДС, query-гарды смет, обход clean через bulk_create. Не дублируют
PriceCalcTest/DateChainTest/CashflowTest из tests.py.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from ProjectContract.models import (
    CashflowEntry, Contract, ContractEstimate, ContractPayments,
    Contractor, EstimateConcept, PaymentTaskLink,
)
from ProjectContract.services import propagate_dates
from ProjectTDL.models import TaskNode
from StaticData.models import Category, ProjectSite, Status


class ContractGuardMixin:
    @classmethod
    def setUpTestData(cls):
        cls.site = ProjectSite.objects.create(name='F3-Объект')
        cls.contractor = Contractor.objects.create(name='F3-Подрядчик')
        cls.contract = Contract.objects.create(
            project_site=cls.site, contractor=cls.contractor,
            name='F3-Договор', price=Decimal('1000000.00'))
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        cls.owner = cls._mkuser()

    @classmethod
    def _mkuser(cls):
        from django.contrib.auth.models import User
        return User.objects.create_user(username='f3_user', password='pw')

    def _pay(self, **kw):
        kw.setdefault('contract', self.contract)
        kw.setdefault('name', 'ПП')
        return ContractPayments.objects.create(**kw)

    def _task(self, price):
        return TaskNode.objects.create(
            owner=self.owner, project_site=self.site, name='T',
            price=price)


class ManualDueSacredTest(ContractGuardMixin, TestCase):
    def test_explicit_due_survives_save(self):
        # Факт: явно заданный due не пересчитывается из start+duration.
        p = self._pay(start_date=date(2026, 1, 1), duration=10,
                      due_date=date(2026, 2, 1), price=Decimal('100'))
        p.refresh_from_db()
        self.assertEqual(p.due_date, date(2026, 2, 1))

    def test_status_toggle_keeps_due_and_autofills_paid(self):
        # Факт: смена статуса не затирает ручной due; paid_amount=price.
        p = self._pay(start_date=date(2026, 1, 1), duration=10,
                      due_date=date(2026, 2, 1), price=Decimal('100'))
        p.status = 'paid'
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.due_date, date(2026, 2, 1))
        self.assertEqual(p.paid_amount, Decimal('100'))
        self.assertTrue(p.made_payment)


class ParentDueNoneTest(ContractGuardMixin, TestCase):
    def test_child_start_untouched_when_parent_has_no_due(self):
        parent = self._pay(name='P')
        child = self._pay(name='C', parent=parent,
                          start_date=date(2026, 5, 1), duration=5)
        child.refresh_from_db()
        self.assertEqual(child.start_date, date(2026, 5, 1))
        self.assertEqual(child.due_date, date(2026, 5, 6))


class PropagateCascadeTest(ContractGuardMixin, TestCase):
    def test_grandchild_recomputed(self):
        gp = self._pay(name='GP', start_date=date(2026, 1, 1),
                       duration=9, price=Decimal('10'))
        child = self._pay(name='CH', parent=gp, duration=5,
                          price=Decimal('10'))
        grand = self._pay(name='GR', parent=child, duration=5,
                          price=Decimal('10'))
        gp.due_date = date(2026, 3, 1)
        gp.save()
        child.refresh_from_db()
        grand.refresh_from_db()
        self.assertEqual(child.start_date, date(2026, 3, 1))
        self.assertEqual(child.due_date, date(2026, 3, 6))
        self.assertEqual(grand.start_date, date(2026, 3, 6))
        self.assertEqual(grand.due_date, date(2026, 3, 11))

    def test_cycle_terminates(self):
        # Факт: цикл родителей не вешает пересчёт (visited-защита).
        a = self._pay(name='A', duration=5, price=Decimal('10'))
        b = self._pay(name='B', parent=a, duration=5, price=Decimal('10'))
        a.parent = b
        a.save()
        updated = propagate_dates(a)
        self.assertLessEqual(updated, 2)


class CashflowIdempotencyTest(ContractGuardMixin, TestCase):
    def test_double_save_same_rows(self):
        p = self._pay(due_date=date(2026, 4, 1), price=Decimal('500'),
                      status='paid', paid_date=date(2026, 4, 2))
        first = sorted(CashflowEntry.objects.filter(
            contract=self.contract).values_list('date', 'amount', 'bucket'))
        p.save()
        second = sorted(CashflowEntry.objects.filter(
            contract=self.contract).values_list('date', 'amount', 'bucket'))
        self.assertEqual(first, second)
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0][2], 'fact')


class EstimateRollupQueryTest(ContractGuardMixin, TestCase):
    def _estimate_with_concepts(self):
        est = ContractEstimate.objects.create(
            contract=self.contract, name='Смета')
        for amount in ('100.00', '200.00', '300.00'):
            EstimateConcept.objects.create(
                estimate=est, name='Поз', amount=Decimal(amount))
        return est

    def test_rollup_amount_single_query(self):
        est = self._estimate_with_concepts()
        with self.assertNumQueries(1):
            total = est.rollup_amount
        self.assertEqual(total, Decimal('600'))

    def test_is_overrun_flag(self):
        est = self._estimate_with_concepts()
        self.assertFalse(est.is_overrun)
        EstimateConcept.objects.create(
            estimate=est, name='Гигант', amount=Decimal('2000000.00'))
        # Факт: оценка читает цену договора из памяти (contract уже подгружен).
        self.assertTrue(est.is_overrun)


class BulkSkipsCleanTest(ContractGuardMixin, TestCase):
    def test_bulk_create_validates_overpay(self):
        # bulk_create валидирует clean(): переплата отклоняется.
        from django.core.exceptions import ValidationError
        task = self._task(Decimal('1000.00'))
        pay = self._pay(price=Decimal('5000.00'))
        pay2 = self._pay(name='ПП2', price=Decimal('5000.00'))
        PaymentTaskLink.objects.create(
            payment=pay, task_node=task, amount_applied=Decimal('600.00'))
        with self.assertRaises(ValidationError):
            PaymentTaskLink.objects.bulk_create([
                PaymentTaskLink(payment=pay2, task_node=task,
                                amount_applied=Decimal('600.00'))])
        from django.db.models import Sum
        total = PaymentTaskLink.objects.filter(task_node=task).aggregate(
            total=Sum('amount_applied'))['total']
        self.assertEqual(total, Decimal('600.00'))

    def test_bulk_create_skip_hatch(self):
        # skip_validation=True — люк для переносов (поведение задокументировано).
        task = self._task(Decimal('1000.00'))
        pay = self._pay(price=Decimal('5000.00'))
        pay2 = self._pay(name='ПП2', price=Decimal('5000.00'))
        PaymentTaskLink.objects.create(
            payment=pay, task_node=task, amount_applied=Decimal('600.00'))
        PaymentTaskLink.objects.bulk_create([
            PaymentTaskLink(payment=pay2, task_node=task,
                            amount_applied=Decimal('600.00'))],
            skip_validation=True)
        from django.db.models import Sum
        total = PaymentTaskLink.objects.filter(task_node=task).aggregate(
            total=Sum('amount_applied'))['total']
        self.assertEqual(total, Decimal('1200.00'))


class UpdateChildrenTest(ContractGuardMixin, TestCase):
    def test_delegates_to_propagate(self):
        # Блок 16: единственный легаси-мутатор — тонкая обёртка propagate.
        from datetime import date
        gp = self._pay(name='GP', start_date=date(2026, 1, 1),
                       duration=9, price=Decimal('10'))
        child = self._pay(name='CH', parent=gp, duration=5,
                          price=Decimal('10'))
        gp.due_date = date(2026, 3, 1)
        gp.save()
        self.assertEqual(gp.update_children(), 1)
        child.refresh_from_db()
        self.assertEqual(child.start_date, date(2026, 3, 1))
