# -*- coding: utf-8 -*-
"""Блок 7: тесты админки договоров (агрегаты, аннотации строк, журнал)."""
from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from ProjectContract.admin import ContractAdmin
from ProjectContract.models import (
    Contract,
    ContractChangeLog,
    ContractPayments,
    Contractor,
)
from StaticData.models import ProjectSite


class ContractAdminFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_superuser(
            username='b7_boss', password='pw', email='b@b.b')
        cls.site = ProjectSite.objects.create(name='B7-Объект')
        cls.contractor = Contractor.objects.create(name='B7-Подрядчик')
        cls.contract = Contract.objects.create(
            project_site=cls.site, contractor=cls.contractor,
            name='B7-Договор', price=Decimal('1000.00'))
        ContractPayments.objects.create(
            contract=cls.contract, name='Оплачен',
            price=Decimal('300.00'), status='paid')
        ContractPayments.objects.create(
            contract=cls.contract, name='План',
            price=Decimal('700.00'), status='planned')

    def _ma(self):
        return ContractAdmin(Contract, AdminSite())

    def _request(self):
        req = RequestFactory().get('/admin/')
        req.user = self.boss
        return req


class RowAggregatesTest(ContractAdminFixtureMixin, TestCase):
    def test_annotated_zero_queries(self):
        # Блок 7: суммы строк едут аннотациями get_queryset, 0 запросов.
        obj = self._ma().get_queryset(self._request()).get(pk=self.contract.pk)
        with self.assertNumQueries(0):
            paid = self._ma().paid_amount(obj)
            unpaid = self._ma().unpaid_amount(obj)
            check = self._ma().status_check(obj)
        self.assertEqual(paid, Decimal('300'))
        self.assertEqual(unpaid, Decimal('700'))
        self.assertEqual(check, Decimal('0'))

    def test_fallback_queries_and_values(self):
        # Вне админского qs — legacy запросы (paid+unpaid+2 внутри check).
        obj = Contract.objects.get(pk=self.contract.pk)
        with self.assertNumQueries(4):
            self.assertEqual(self._ma().paid_amount(obj), Decimal('300'))
            self.assertEqual(self._ma().unpaid_amount(obj), Decimal('700'))
            self.assertEqual(self._ma().status_check(obj), Decimal('0'))

    def test_fk_columns_no_extra_queries(self):
        # Блок 23: project_site/contractor/client идут JOIN одним запросом.
        qs = self._ma().get_queryset(self._request())
        with self.assertNumQueries(1):
            objs = list(qs)
            for o in objs:
                (o.project_site.name, o.contractor.name,
                 o.client.name if o.client_id else None)


class ChangelistTotalsTest(ContractAdminFixtureMixin, TestCase):
    def test_changelist_totals(self):
        self.client.force_login(self.boss)
        resp = self.client.get('/admin/ProjectContract/contract/')
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context
        self.assertEqual(ctx['total_price'], Decimal('1000'))
        self.assertEqual(ctx['total_paid'], Decimal('300'))
        self.assertEqual(ctx['total_unpaid'], Decimal('700'))
        self.assertEqual(ctx['total_status'], Decimal('0'))

    def test_empty_changelist_no_crash(self):
        # Факт: пустая выдача давала None-сумму и TypeError (500).
        # Исправлено or 0 — гард фиксирует 200.
        ContractPayments.objects.all().delete()
        Contract.objects.all().delete()
        self.client.force_login(self.boss)
        resp = self.client.get('/admin/ProjectContract/contract/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_status'], 0)


class AdminJournalTest(ContractAdminFixtureMixin, TestCase):
    def test_save_logs_created_updated(self):
        req = self._request()
        obj = Contract(project_site=self.site, contractor=self.contractor,
                       name='J', price=Decimal('10'))
        self._ma().save_model(req, obj, form=None, change=False)
        self._ma().save_model(req, obj, form=None, change=True)
        actions = list(ContractChangeLog.objects.filter(
            contract=obj).order_by('id').values_list('action', flat=True))
        self.assertEqual(actions, ['created', 'updated'])

    def test_delete_logs_before_remove(self):
        # Факт: запись deleted создаётся ДО удаления; FK SET_NULL —
        # строка переживает договор с contract=NULL.
        req = self._request()
        pk, price = self.contract.pk, self.contract.price
        self._ma().delete_model(req, self.contract)
        row = ContractChangeLog.objects.get(action='deleted')
        self.assertIsNone(row.contract)
        self.assertIn(f'id={pk}', row.details)
        self.assertIn(str(price), row.details)
