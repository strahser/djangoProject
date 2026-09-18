"""Ф0: регресс-тесты типизированных расчётов и цепочки дат (без eval/рекурсии)."""
import datetime
from decimal import Decimal

from django.test import TestCase

from ProjectContract.models import Contract, Contractor, ContractPayments, ContractChangeLog, Tag
from ProjectContract.services import compute_price, parse_simple_formula, propagate_dates
from StaticData.models import ProjectSite


class PriceCalcTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = ProjectSite.objects.create(name='Тест-объект')
        contractor = Contractor.objects.create(name='Тест-подрядчик')
        cls.contract = Contract.objects.create(
            project_site=site, contractor=contractor,
            name='Тест-договор', price=Decimal('1000000.00'))

    def _mk(self, **kw):
        kw.setdefault('contract', self.contract)
        kw.setdefault('name', 'пл')
        return ContractPayments(**kw)

    def test_percent_of_contract(self):
        p = self._mk(calc_type='percent_of_contract', percent=0.25)
        self.assertEqual(compute_price(p), Decimal('250000.00'))

    def test_percent_of_base(self):
        p = self._mk(calc_type='percent_of_base', percent=0.4,
                     base_amount=Decimal('3050000.00'))
        self.assertEqual(compute_price(p), Decimal('1220000.00'))

    def test_manual_keeps_price(self):
        p = self._mk(calc_type='manual', price=Decimal('123.45'))
        self.assertIsNone(compute_price(p))

    def test_missing_base_keeps_price(self):
        p = self._mk(calc_type='percent_of_base', percent=0.5, base_amount=None,
                     price=Decimal('777.00'))
        self.assertIsNone(compute_price(p))

    def test_save_applies_calc(self):
        p = self._mk(calc_type='percent_of_contract', percent=0.1,
                     price=Decimal('0'), start_date=datetime.date(2026, 1, 1),
                     duration=5)
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.price, Decimal('100000.00'))
        self.assertEqual(p.due_date, datetime.date(2026, 1, 6))

    def test_parse_simple_formula(self):
        self.assertEqual(parse_simple_formula('2000000*0.5'),
                         (Decimal('2000000'), Decimal('0.5')))
        self.assertEqual(parse_simple_formula('  3050000 * 0.1 '),
                         (Decimal('3050000'), Decimal('0.1')))
        self.assertIsNone(parse_simple_formula('instance.contract.price*0.5'))
        self.assertIsNone(parse_simple_formula('__import__("os").system(1)'))
        self.assertIsNone(parse_simple_formula(None))


class DateChainTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = ProjectSite.objects.create(name='Тест-объект')
        contractor = Contractor.objects.create(name='Тест-подрядчик')
        cls.contract = Contract.objects.create(
            project_site=site, contractor=contractor,
            name='Тест-договор', price=Decimal('100.00'))

    def test_chain_propagates_without_recursion(self):
        root = ContractPayments.objects.create(
            contract=self.contract, name='root', calc_type='manual',
            price=Decimal('10'), start_date=datetime.date(2026, 3, 1), duration=10)
        child = ContractPayments.objects.create(
            contract=self.contract, name='child', calc_type='manual',
            price=Decimal('10'), parent=root,
            start_date=datetime.date(2000, 1, 1), duration=5)
        grand = ContractPayments.objects.create(
            contract=self.contract, name='grand', calc_type='manual',
            price=Decimal('10'), parent=child,
            start_date=datetime.date(2000, 1, 1), duration=2)
        # Сдвигаем корень: цепочка должна перестроиться одним save.
        root.start_date = datetime.date(2026, 4, 1)
        root.save()
        child.refresh_from_db()
        grand.refresh_from_db()
        self.assertEqual(root.due_date, datetime.date(2026, 4, 11))
        self.assertEqual(child.start_date, datetime.date(2026, 4, 11))
        self.assertEqual(child.due_date, datetime.date(2026, 4, 16))
        self.assertEqual(grand.start_date, datetime.date(2026, 4, 16))
        self.assertEqual(grand.due_date, datetime.date(2026, 4, 18))

    def test_propagate_returns_count(self):
        root = ContractPayments.objects.create(
            contract=self.contract, name='root', calc_type='manual',
            price=Decimal('10'), start_date=datetime.date(2026, 1, 1), duration=3)
        ContractPayments.objects.create(
            contract=self.contract, name='c1', calc_type='manual',
            price=Decimal('5'), parent=root,
            start_date=datetime.date(2026, 1, 4), duration=2)
        self.assertEqual(propagate_dates(root), 1)


class PaymentFormTest(TestCase):
    def test_percent_of_base_requires_base(self):
        from ProjectContract.form import ContractPaymentsAdminForm
        form = ContractPaymentsAdminForm(data={
            'name': 'x', 'contract': '', 'price': '10',
            'calc_type': 'percent_of_base', 'percent': '0.5'})
        self.assertFalse(form.is_valid())
        self.assertIn('base_amount', form.errors)


class PaymentStatusTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = ProjectSite.objects.create(name='Тест-объект')
        contractor = Contractor.objects.create(name='Тест-подрядчик')
        cls.contract = Contract.objects.create(
            project_site=site, contractor=contractor,
            name='Тест-договор', price=Decimal('1000.00'))

    def test_status_syncs_made_payment(self):
        p = ContractPayments.objects.create(
            contract=self.contract, name='a', calc_type='manual',
            price=Decimal('100'), status='paid')
        self.assertTrue(p.made_payment)
        self.assertEqual(p.paid_amount, Decimal('100'))
        p.status = 'planned'
        p.save()
        p.refresh_from_db()
        self.assertFalse(p.made_payment)

    def test_percent_of_parent(self):
        from ProjectContract.services import compute_price
        parent = ContractPayments.objects.create(
            contract=self.contract, name='par', calc_type='manual',
            price=Decimal('800'))
        child = ContractPayments(
            contract=self.contract, name='ch', calc_type='percent_of_parent',
            percent=0.5, parent=parent)
        self.assertEqual(compute_price(child), Decimal('400.00'))

    def test_toggle_flips_status_and_logs(self):
        from django.contrib.auth.models import User
        from ProjectContract.models import ContractChangeLog
        user = User.objects.create_user('toggler', 't@t.t', 'pw')
        self.client.force_login(user)
        p = ContractPayments.objects.create(
            contract=self.contract, name='a', calc_type='manual',
            price=Decimal('100'), status='planned')
        r = self.client.post(f'/contract/payment/{p.pk}/toggle/')
        self.assertEqual(r.json()['made'], True)
        p.refresh_from_db()
        self.assertEqual(p.status, 'paid')
        self.assertIsNotNone(p.paid_date)
        self.assertTrue(ContractChangeLog.objects
                        .filter(payment=p, action='paid', user=user).exists())
        r = self.client.post(f'/contract/payment/{p.pk}/toggle/')
        self.assertEqual(r.json()['made'], False)


class ContractDomainTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = ProjectSite.objects.create(name='Тест-объект')
        contractor = Contractor.objects.create(name='Тест-подрядчик')
        client = Contractor.objects.create(name='Тест-заказчик')
        cls.gen = Contract.objects.create(
            project_site=site, contractor=contractor, client=client,
            name='Генподряд', number='ГП-1', price=Decimal('1000.00'))
        cls.sub = Contract.objects.create(
            project_site=site, contractor=contractor,
            name='Субподряд', parent=cls.gen, price=Decimal('400.00'))

    def test_rollup_includes_children(self):
        from ProjectContract.services import contract_rollup
        ContractPayments.objects.create(
            contract=self.gen, name='g', calc_type='manual',
            price=Decimal('600'), status='paid')
        ContractPayments.objects.create(
            contract=self.sub, name='s', calc_type='manual',
            price=Decimal('100'), status='guaranteed')
        roll = contract_rollup(self.gen)
        self.assertEqual(roll['contracts'], 2)
        self.assertEqual(roll['price'], Decimal('1400.00'))
        self.assertEqual(roll['paid'], Decimal('600'))
        self.assertEqual(roll['guaranteed'], Decimal('100'))

    def test_transition_valid_and_logged(self):
        from django.contrib.auth.models import User
        from ProjectContract.models import ContractChangeLog
        from ProjectContract.services import transition_contract
        user = User.objects.create_user('boss', 'b@b.b', 'pw')
        transition_contract(self.gen, 'suspended', user=user)
        self.gen.refresh_from_db()
        self.assertEqual(self.gen.status, 'suspended')
        self.assertTrue(ContractChangeLog.objects
                        .filter(contract=self.gen, action='status',
                                user=user).exists())
        with self.assertRaises(ValueError):
            transition_contract(self.gen, 'draft', user=user)

    def test_closed_is_terminal(self):
        from ProjectContract.services import transition_contract
        self.gen.status = 'closed'
        self.gen.save()
        with self.assertRaises(ValueError):
            transition_contract(self.gen, 'active')


class CashflowTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = ProjectSite.objects.create(name='Тест-объект')
        contractor = Contractor.objects.create(name='Тест-подрядчик')
        cls.contract = Contract.objects.create(
            project_site=site, contractor=contractor,
            name='Тест-ДДС', price=Decimal('10000.00'))
        cls.paid = ContractPayments.objects.create(
            contract=cls.contract, name='opl', calc_type='manual',
            price=Decimal('1000'), status='paid',
            paid_amount=Decimal('1000'),
            paid_date=datetime.date(2026, 5, 10),
            due_date=datetime.date(2026, 5, 1))
        cls.guar = ContractPayments.objects.create(
            contract=cls.contract, name='gar', calc_type='manual',
            price=Decimal('2000'), status='guaranteed',
            due_date=datetime.date(2026, 6, 1))
        cls.part = ContractPayments.objects.create(
            contract=cls.contract, name='part', calc_type='manual',
            price=Decimal('1000'), status='partially_paid',
            paid_amount=Decimal('400'),
            paid_date=datetime.date(2026, 5, 20),
            due_date=datetime.date(2026, 7, 1))

    def test_rebuild_buckets(self):
        from ProjectContract.models import CashflowEntry
        rows = CashflowEntry.objects.filter(contract=self.contract)\
            .order_by('bucket', 'amount')
        kinds = [(r.bucket, r.amount, str(r.date)) for r in rows]
        self.assertIn(('fact', Decimal('1000.00'), '2026-05-10'), kinds)
        self.assertIn(('guaranteed', Decimal('2000.00'), '2026-06-01'), kinds)
        self.assertIn(('fact', Decimal('400.00'), '2026-05-20'), kinds)
        self.assertIn(('guaranteed', Decimal('600.00'), '2026-07-01'), kinds)

    def test_signal_rebuilds_on_save(self):
        from ProjectContract.models import CashflowEntry
        self.guar.status = 'paid'
        self.guar.save()
        self.assertTrue(CashflowEntry.objects.filter(
            payment=self.guar, bucket='fact').exists())
        self.assertFalse(CashflowEntry.objects.filter(
            payment=self.guar, bucket='guaranteed').exists())

    def test_cashflow_view(self):
        from django.contrib.auth.models import User
        user = User.objects.create_user('viewer', 'v@v.v', 'pw')
        self.client.force_login(user)
        r = self.client.get('/contract/cashflow/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Тест-ДДС')
        self.assertContains(r, 'Гарантировано')
        r = self.client.get('/contract/cashflow/?scale=quarter')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'К2.2026')


class DashboardReportTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        site = ProjectSite.objects.create(name='Тест-объект')
        contractor = Contractor.objects.create(name='Тест-подрядчик')
        cls.contract = Contract.objects.create(
            project_site=site, contractor=contractor,
            name='Тест-отчёт', number='Т-1', price=Decimal('1000.00'))
        ContractPayments.objects.create(
            contract=cls.contract, name='opl', calc_type='manual',
            price=Decimal('400'), status='paid',
            paid_amount=Decimal('400'),
            paid_date=datetime.date(2026, 5, 10),
            due_date=datetime.date(2026, 5, 1))
        ContractPayments.objects.create(
            contract=cls.contract, name='gar', calc_type='manual',
            price=Decimal('300'), status='guaranteed',
            due_date=datetime.date(2026, 6, 1))

    def test_dashboard_report(self):
        from django.contrib.auth.models import User
        user = User.objects.create_user('rep', 'r@r.r', 'pw')
        self.client.force_login(user)
        r = self.client.get('/contract/dashboard/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Как это работает')
        self.assertContains(r, 'memoModal')
        self.assertContains(r, 'Действующий')
        self.assertContains(r, 'Оплачен')
        self.assertContains(r, 'Гарантирован')
        self.assertContains(r, '300')

    def test_help_page(self):
        from django.contrib.auth.models import User
        user = User.objects.create_user('rep2', 'r2@r.r', 'pw')
        self.client.force_login(user)
        r = self.client.get('/contract/help/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Субподряд')
        self.assertContains(r, 'ручной срок')


class PaymentTaskLinkTest(TestCase):
    """DMC-2: связь платёж <-> работа (TaskNode)."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User
        site = ProjectSite.objects.create(name='Тест-объект-связь')
        contractor = Contractor.objects.create(name='Тест-подрядчик')
        cls.user = User.objects.create_user('linker', 'l@l.l', 'pw')
        cls.contract = Contract.objects.create(
            project_site=site, contractor=contractor,
            name='Тест-договор', price=Decimal('10000.00'))
        cls.payment = ContractPayments.objects.create(
            contract=cls.contract, name='пл-связь', calc_type='manual',
            price=Decimal('3000'), status='paid', paid_amount=Decimal('3000'))
        from ProjectTDL.models import TaskNode
        cls.task = TaskNode.objects.create(
            name='задача-связь', owner=cls.user,
            project_site=site, status=None, category=None,
            price=Decimal('1000'))

    def _mk(self, **kw):
        from ProjectContract.models import PaymentTaskLink
        kw.setdefault('payment', self.payment)
        kw.setdefault('task_node', self.task)
        kw.setdefault('amount_applied', Decimal('500'))
        return PaymentTaskLink(**kw)

    def test_create_link(self):
        lnk = self._mk()
        lnk.save()
        self.assertEqual(lnk.task_node.total_paid, Decimal('500'))

    def test_total_paid_sum(self):
        lnk = self._mk(amount_applied=Decimal('100'))
        lnk.save()
        from ProjectContract.models import ContractPayments, PaymentTaskLink
        other = ContractPayments.objects.create(
            contract=self.contract, name='пл-сумма', calc_type='manual',
            price=Decimal('900'))
        PaymentTaskLink.objects.create(
            payment=other, task_node=self.task, amount_applied=Decimal('200'))
        self.assertEqual(lnk.task_node.total_paid, Decimal('300'))

    def test_validation_above_task_price(self):
        from django.core.exceptions import ValidationError
        from ProjectContract.models import PaymentTaskLink
        PaymentTaskLink.objects.create(
            payment=self.payment, task_node=self.task, amount_applied=Decimal('600'))
        with self.assertRaises(ValidationError):
            PaymentTaskLink.objects.create(
                payment=self.payment, task_node=self.task, amount_applied=Decimal('600'))
        with self.assertRaises(ValidationError):
            PaymentTaskLink.objects.create(
                payment=self.payment, task_node=self.task, amount_applied=Decimal('401'))

    def test_validation_above_contract_price(self):
        from django.core.exceptions import ValidationError
        from ProjectContract.models import PaymentTaskLink
        with self.assertRaises(ValidationError):
            PaymentTaskLink.objects.create(
                payment=self.payment, task_node=self.task,
                amount_applied=Decimal('11000.00'))

    def test_is_overpaid_flag(self):
        from ProjectContract.models import PaymentTaskLink
        from ProjectTDL.models import TaskNode
        task2 = TaskNode.objects.create(
            name='task2', owner=self.user, project_site=self.task.project_site,
            status=None, category=None, price=Decimal('500'))
        PaymentTaskLink.objects.create(
            payment=self.payment, task_node=task2, amount_applied=Decimal('300'))
        self.assertFalse(task2.is_overpaid)
        # Дешевеем задачу: существующая сумма привязок (300) становится больше цены (200).
        task2.price = Decimal('200')
        task2.save()
        task2.refresh_from_db()
        self.assertTrue(task2.is_overpaid)

    def test_contract_totals_include_links(self):
        from ProjectContract.models import PaymentTaskLink
        from ProjectContract.services import contract_totals
        PaymentTaskLink.objects.create(
            payment=self.payment, task_node=self.task, amount_applied=Decimal('700'))
        t = contract_totals(self.contract)
        self.assertEqual(t['linked_total'], Decimal('700'))
        self.assertEqual(t['task_links_count'], 1)

    def test_contract_rollup_include_links(self):
        from ProjectContract.models import PaymentTaskLink
        from ProjectContract.services import contract_rollup
        PaymentTaskLink.objects.create(
            payment=self.payment, task_node=self.task, amount_applied=Decimal('700'))
        from ProjectTDL.models import TaskNode
        sub = Contract.objects.create(
            project_site=self.task.project_site,
            contractor=Contractor.objects.create(name='суб-связь'),
            parent=self.contract, name='суб', price=Decimal('500'))
        p2 = ContractPayments.objects.create(
            contract=sub, name='пл3', calc_type='manual', price=Decimal('200'))
        task2 = TaskNode.objects.create(
            name='task3', owner=self.user, project_site=self.task.project_site,
            status=None, category=None, price=Decimal('200'))
        PaymentTaskLink.objects.create(
            payment=p2, task_node=task2, amount_applied=Decimal('200'))
        roll = contract_rollup(self.contract)
        self.assertEqual(roll['linked_total'], Decimal('900'))
        self.assertEqual(roll['task_links_count'], 2)

    def test_admin_inline_render(self):
        from django.contrib.auth.models import User
        from ProjectContract.models import PaymentTaskLink
        PaymentTaskLink.objects.create(
            payment=self.payment, task_node=self.task, amount_applied=Decimal('100'))
        staff = User.objects.create_user('staff', 's@s.s', 'pw', is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        r = self.client.get(f'/admin/ProjectContract/contractpayments/{self.payment.pk}/change/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'amount_applied')


class ContractEstimateTest(TestCase):
    """DMC-3: смета договора + позиции (EstimateConcept) + rollup/перерасход."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User
        from ProjectTDL.models import TaskNode
        site = ProjectSite.objects.create(name='Тест-объект-смета')
        contractor = Contractor.objects.create(name='Тест-подрядчик')
        cls.user = User.objects.create_user('estimator', 'e@e.e', 'pw')
        cls.contract = Contract.objects.create(
            project_site=site, contractor=contractor,
            name='Тест-договор-смета', price=Decimal('10000.00'))
        cls.task = TaskNode.objects.create(
            name='задача-смета', owner=cls.user,
            project_site=site, status=None, category=None,
            price=Decimal('1000'))

    def _est(self):
        from ProjectContract.models import ContractEstimate
        return ContractEstimate.objects.create(
            contract=self.contract, name='Смета 1', status='draft')

    def _concept(self, est=None, **kw):
        from ProjectContract.models import EstimateConcept
        kw.setdefault('estimate', est or self._est())
        kw.setdefault('name', 'Позиция')
        kw.setdefault('amount', Decimal('600.00'))
        return EstimateConcept.objects.create(**kw)

    def test_create_estimate_total_rolls_up(self):
        est = self._est()
        self.assertEqual(est.total_amount, Decimal('0.00'))
        self._concept(est=est, amount=Decimal('500.00'))
        self._concept(est=est, name='Позиция 2',
                      amount=Decimal('250.00'), task_node=self.task)
        est.refresh_from_db()
        self.assertEqual(est.total_amount, Decimal('750.00'))
        self.assertEqual(est.rollup_amount, Decimal('750.00'))

    def test_amount_computed_from_quantity_price(self):
        est = self._est()
        concept = self._concept(est=est, quantity=Decimal('10'),
                                unit_price=Decimal('50'), amount=Decimal('0'))
        self.assertEqual(concept.amount, Decimal('500.00'))
        est.refresh_from_db()
        self.assertEqual(est.total_amount, Decimal('500.00'))

    def test_rollup_method_saves_total(self):
        est = self._est()
        self._concept(est=est, amount=Decimal('333.00'))
        self._concept(est=est, name='B', amount=Decimal('222.00'))
        est.refresh_from_db()
        result = est.rollup()
        est.refresh_from_db()
        self.assertEqual(result, Decimal('555.00'))
        self.assertEqual(est.total_amount, Decimal('555.00'))

    def test_is_overrun_flag(self):
        est = self._est()
        self._concept(est=est, amount=Decimal('8000.00'))
        self.assertFalse(est.is_overrun)
        self._concept(est=est, name='B', amount=Decimal('3000.00'))
        est.refresh_from_db()
        self.assertEqual(est.total_amount, Decimal('11000.00'))
        self.assertTrue(est.is_overrun)

    def test_contract_estimate_fk_links(self):
        est = self._est()
        self.contract.estimate = est
        self.contract.save(update_fields=['estimate'])
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.estimate, est)

    def test_contract_totals_include_estimates(self):
        from ProjectContract.services import contract_totals
        est = self._est()
        self._concept(est=est, amount=Decimal('500.00'))
        self._concept(est=est, name='B', amount=Decimal('12000.00'))
        t = contract_totals(self.contract)
        self.assertEqual(t['estimate_total'], Decimal('12500.00'))
        self.assertEqual(t['estimate_overrun'], 1)

    def test_contract_rollup_include_sub_estimates(self):
        from ProjectContract.models import ContractEstimate, EstimateConcept
        from ProjectContract.services import contract_rollup
        sub = Contract.objects.create(
            project_site=self.task.project_site,
            contractor=Contractor.objects.create(name='суб-смета'),
            parent=self.contract, name='суб', price=Decimal('500'))
        est1 = self._est()
        self._concept(est=est1, amount=Decimal('600.00'))
        est2 = ContractEstimate.objects.create(
            contract=sub, name='смета суба', status='draft')
        EstimateConcept.objects.create(
            estimate=est2, name='П', amount=Decimal('400.00'))
        roll = contract_rollup(self.contract)
        self.assertEqual(roll['estimate_total'], Decimal('1000.00'))
        self.assertEqual(roll['estimate_overrun'], 0)

    def test_payment_link_blocked_above_concept(self):
        from django.core.exceptions import ValidationError
        from ProjectContract.models import ContractPayments, PaymentTaskLink
        est = self._est()
        self._concept(est=est, amount=Decimal('400.00'), task_node=self.task)
        pay = ContractPayments.objects.create(
            contract=self.contract, name='пл-смета', calc_type='manual',
            price=Decimal('3000'), status='paid', paid_amount=Decimal('3000'))
        PaymentTaskLink.objects.create(
            payment=pay, task_node=self.task, amount_applied=Decimal('300'))
        with self.assertRaises(ValidationError):
            PaymentTaskLink.objects.create(
                payment=pay, task_node=self.task, amount_applied=Decimal('200'))

    def test_primary_estimate_fk_related_name(self):
        est = self._est()
        self.contract.estimate = est
        self.contract.save(update_fields=['estimate'])
        self.assertEqual(est.contracts_main.filter(pk=self.contract.pk).count(), 1)

    def test_admin_estimate_render(self):
        from django.contrib.auth.models import User
        est = self._est()
        self._concept(est=est, amount=Decimal('600.00'))
        staff = User.objects.create_user(
            'eststaff', 'es@s.s', 'pw', is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        r = self.client.get(f'/admin/ProjectContract/contractestimate/{est.pk}/change/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'estimateconcept')


class ContractDetailTest(TestCase):
    """DMC-4: карточка договора с HTMX-вкладками."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User
        from ProjectTDL.models import TaskNode
        cls.user = User.objects.create_user('card', 'c@c.c', 'pw')
        site = ProjectSite.objects.create(name='Тест-объект-карточка')
        contractor = Contractor.objects.create(name='Тест-подрядчик')
        cls.contract = Contract.objects.create(
            project_site=site, contractor=contractor,
            name='Тест-договор-карточка', number='К-1', price=Decimal('10000.00'))
        cls.payment = ContractPayments.objects.create(
            contract=cls.contract, name='пл-карточка', calc_type='manual',
            price=Decimal('4000'), status='paid', paid_amount=Decimal('4000'))
        cls.task = TaskNode.objects.create(
            name='задача-карточка', owner=cls.user,
            project_site=site, status=None, category=None,
            contract=cls.contract, price=Decimal('1500'))

    def test_detail_page_renders_tabs(self):
        self.client.force_login(self.user)
        r = self.client.get(f'/contract/{self.contract.pk}/')
        self.assertEqual(r.status_code, 200)
        for label in ('Оплаты', 'Работы', 'История', 'Документы'):
            self.assertContains(r, label)
        self.assertContains(r, 'пл-карточка')

    def test_tab_payments_fragment(self):
        from ProjectContract.models import PaymentTaskLink
        PaymentTaskLink.objects.create(
            payment=self.payment, task_node=self.task, amount_applied=Decimal('600'))
        self.client.force_login(self.user)
        r = self.client.get(f'/contract/{self.contract.pk}/tab/payments/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'пл-карточка')
        self.assertContains(r, 'Итого')

    def test_tab_tasks_fragment(self):
        self.client.force_login(self.user)
        r = self.client.get(f'/contract/{self.contract.pk}/tab/tasks/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'задача-карточка')
        self.assertContains(r, 'Подзадачи')

    def test_tab_history_fragment(self):
        from ProjectContract.models import ContractChangeLog
        ContractChangeLog.objects.create(
            contract=self.contract, action='status',
            details='draft → active', user=self.user)
        self.client.force_login(self.user)
        r = self.client.get(f'/contract/{self.contract.pk}/tab/history/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'status')
        self.assertContains(r, 'draft → active')

    def test_tab_docs_placeholder(self):
        self.client.force_login(self.user)
        r = self.client.get(f'/contract/{self.contract.pk}/tab/docs/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Загрузить')

    def test_bad_tab_404(self):
        self.client.force_login(self.user)
        r = self.client.get(f'/contract/{self.contract.pk}/tab/unknown/')
        self.assertEqual(r.status_code, 404)

    def test_toggle_via_card_tab(self):
        p2 = ContractPayments.objects.create(
            contract=self.contract, name='пл-tab', calc_type='manual',
            price=Decimal('500'), status='planned')
        self.client.force_login(self.user)
        r = self.client.post(f'/contract/payment/{p2.pk}/toggle/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['made'], True)
        p2.refresh_from_db()
        self.assertEqual(p2.status, 'paid')


class CashflowChartTest(TestCase):
    """DMC-1: агрегация данных Chart.js + рендер страницы ДДС."""

    @classmethod
    def setUpTestData(cls):
        site = ProjectSite.objects.create(name='Тест-объект-график')
        contractor = Contractor.objects.create(name='Тест-подрядчик')
        cls.contract = Contract.objects.create(
            project_site=site, contractor=contractor,
            name='Тест-ДДС-график', price=Decimal('10000.00'))
        cls.paid = ContractPayments.objects.create(
            contract=cls.contract, name='opl', calc_type='manual',
            price=Decimal('2000'), status='paid', paid_amount=Decimal('2000'),
            paid_date=datetime.date(2026, 5, 10),
            due_date=datetime.date(2026, 5, 1))
        cls.guar = ContractPayments.objects.create(
            contract=cls.contract, name='gar', calc_type='manual',
            price=Decimal('3000'), status='guaranteed',
            due_date=datetime.date(2026, 6, 1))
        cls.like = ContractPayments.objects.create(
            contract=cls.contract, name='like', calc_type='manual',
            price=Decimal('1000'), status='high_prob',
            due_date=datetime.date(2026, 6, 5))
        cls.plan = ContractPayments.objects.create(
            contract=cls.contract, name='plan', calc_type='manual',
            price=Decimal('4000'), status='planned',
            due_date=datetime.date(2026, 7, 1))

    def test_pure_aggregation(self):
        from ProjectContract.views import _build_cashflow_chart
        totals = {
            'fact': {'k-a': 2000}, 'guaranteed': {'k-a': 100, 'k-b': 90},
            'likely': {'k-a': 50}, 'planned': {'k-a': 40},
        }
        periods = [{'key': 'k-a', 'label': '05.2026'},
                   {'key': 'k-b', 'label': '06.2026'}]
        rows = [{'id': 7, 'name': 'Д-1',
                 'cells': {'fact': {'k-a': 2000},
                           'guaranteed': {'k-a': 100, 'k-b': 90},
                           'likely': {'k-a': 50},
                           'planned': {'k-a': 40}}}]
        chart = _build_cashflow_chart(
            totals,
            {'fact': 'Факт', 'guaranteed': 'Гарантировано',
             'likely': 'Вероятно', 'planned': 'Запланировано'},
            periods, rows)
        self.assertEqual(chart['labels'], ['05.2026', '06.2026'])
        by_code = {b['code']: b['values'] for b in chart['buckets']}
        self.assertEqual(by_code['fact'], [2000.0, 0.0])
        self.assertEqual(by_code['guaranteed'], [100.0, 90.0])
        # Прогноз = гарантировано + вероятно (по периодам).
        self.assertEqual(chart['forecast'], [150.0, 90.0])
        self.assertIn('7', chart['contracts'])
        self.assertEqual(chart['contracts']['7']['name'], 'Д-1')
        self.assertEqual(chart['contracts']['7']['buckets']['guaranteed'],
                         [100.0, 90.0])

    def test_view_renders_chart_container(self):
        from django.contrib.auth.models import User
        user = User.objects.create_user('cfview', 'cf@v.v', 'pw')
        self.client.force_login(user)
        r = self.client.get('/contract/cashflow/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'cfChart')
        self.assertContains(r, 'chart.umd.min.js')
        self.assertContains(r, 'Прогноз')
        r2 = self.client.get('/contract/cashflow/?scale=quarter')
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, 'cfChart')


class ContractStageLogTest(TestCase):
    """DMC-5: этапы договора, переходы, напоминания."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User
        from ProjectContract.models import ContractStageLog
        site = ProjectSite.objects.create(name='Тест-этапы')
        contractor = Contractor.objects.create(name='Подрядчик-этапы')
        cls.contract = Contract.objects.create(
            project_site=site, contractor=contractor,
            name='Д-этапы', price=Decimal('1000'), status='active',
            stage='negotiation')
        cls.user = User.objects.create_user('stageuser', 'st@st.st', 'pw')
        ContractStageLog.objects.create(
            contract=cls.contract, stage='negotiation',
            date=datetime.date(2026, 1, 10), user=cls.user)

    def _refresh(self):
        self.contract.refresh_from_db()
        return self.contract

    def test_initial_stage_from_migration(self):
        c = self._refresh()
        self.assertEqual(c.stage, 'negotiation')
        self.assertTrue(c.stage_logs.filter(stage='negotiation').exists())

    def test_transition_forward(self):
        from ProjectContract.services import transition_contract_stage
        transition_contract_stage(self.contract, 'signing', notes='подписали', user=self.user)
        c = self._refresh()
        self.assertEqual(c.stage, 'signing')
        self.assertTrue(c.stage_logs.filter(stage='signing', notes='подписали').exists())

    def test_transition_far_forward(self):
        from ProjectContract.services import transition_contract_stage
        transition_contract_stage(self.contract, 'final_payment')
        c = self._refresh()
        self.assertEqual(c.stage, 'final_payment')

    def test_transition_backward_not_allowed(self):
        from ProjectContract.services import transition_contract_stage
        transition_contract_stage(self.contract, 'execution')
        with self.assertRaises(ValueError):
            transition_contract_stage(self.contract, 'signing')

    def test_transition_backward_from_acceptance_allowed(self):
        from ProjectContract.services import transition_contract_stage
        transition_contract_stage(self.contract, 'acceptance')
        transition_contract_stage(self.contract, 'execution')
        self.assertEqual(self._refresh().stage, 'execution')

    def test_transition_closed_forbidden(self):
        from ProjectContract.services import transition_contract_stage
        with self.assertRaises(ValueError):
            transition_contract_stage(self.contract, 'closed')

    def test_status_restriction(self):
        from ProjectContract.services import transition_contract_stage
        self.contract.status = 'draft'
        self.contract.save(update_fields=['status'])
        with self.assertRaises(ValueError):
            transition_contract_stage(self.contract, 'execution')

    def test_schedule_next_step(self):
        from ProjectContract.services import schedule_contract_stage
        schedule_contract_stage(self.contract, 'signing',
                                date=datetime.date(2026, 12, 1), user=self.user)
        c = self._refresh()
        self.assertEqual(c.next_step_date, datetime.date(2026, 12, 1))
        self.assertTrue(c.stage_logs.filter(is_next_step=True, stage='signing').exists())

    def test_tab_stages_renders(self):
        from django.contrib.auth.models import User
        u = User.objects.create_user('stview', 'sv@sv.v', 'pw')
        self.client.force_login(u)
        r = self.client.get(f'/contract/{self.contract.pk}/tab/stages/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Этап')
        self.assertContains(r, 'Переговоры')

    def test_overdue_steps_counted(self):
        from datetime import date as _d
        from ProjectContract.services import schedule_contract_stage, contract_totals
        schedule_contract_stage(self.contract, 'execution', date=_d(2020, 1, 1))
        c = self._refresh()
        totals = contract_totals(c)
        self.assertGreater(totals['overdue_steps'], 0)

    def test_check_stage_reminders(self):
        import io
        from django.core.management import call_command
        from ProjectContract.services import schedule_contract_stage
        schedule_contract_stage(self.contract, 'advance',
                                date=datetime.date(2020, 6, 1), user=self.user)
        out = io.StringIO()
        call_command('check_stage_reminders', stdout=out, stderr=io.StringIO())
        self.assertIn('1', out.getvalue())


class ContractAPITest(TestCase):
    """DMC-6: JSON API /api/v1/contracts/ + /api/v1/payments/."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User
        from rest_framework.authtoken.models import Token
        cls.user = User.objects.create_user('apiuser', 'api@u.u', 'pw', is_staff=True)
        cls.token, _ = Token.objects.get_or_create(user=cls.user)
        cls.site = ProjectSite.objects.create(name='API-site')
        cls.contractor = Contractor.objects.create(name='API-contractor')
        cls.contract = Contract.objects.create(
            project_site=cls.site, contractor=cls.contractor,
            name='API-contract', number='AP-01',
            price=Decimal('5000.00'), status='active', stage='execution')
        cls.payment = ContractPayments.objects.create(
            contract=cls.contract, name='API-payment', calc_type='manual',
            price=Decimal('1500'), status='planned')

    def _auth(self):
        return f'Token {self.token.key}'

    def test_list_contracts_readonly(self):
        r = self.client.get('/api/v1/contracts/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], 'API-contract')

    def test_retrieve_contract(self):
        r = self.client.get(f'/api/v1/contracts/{self.contract.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['name'], 'API-contract')
        self.assertIn('stage_logs', r.json())

    def test_create_contract(self):
        r = self.client.post('/api/v1/contracts/', data={
            'project_site': self.site.pk,
            'contractor': self.contractor.pk,
            'name': 'New-contract',
            'price': '3000.00',
            'status': 'draft',
            'stage': 'negotiation',
        }, content_type='application/json',
           HTTP_AUTHORIZATION=self._auth())
        self.assertEqual(r.status_code, 201)
        self.assertTrue(Contract.objects.filter(name='New-contract').exists())

    def test_create_contract_logged(self):
        self.client.post('/api/v1/contracts/', data={
            'project_site': self.site.pk,
            'contractor': self.contractor.pk,
            'name': 'Logged-contract',
            'price': '1000.00',
            'status': 'draft', 'stage': 'negotiation',
        }, content_type='application/json',
           HTTP_AUTHORIZATION=self._auth())
        self.assertTrue(ContractChangeLog.objects.filter(
            contract__name='Logged-contract', action='api:create').exists())

    def test_update_contract(self):
        r = self.client.patch(f'/api/v1/contracts/{self.contract.pk}/',
                              data={'price': '9999.00'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=self._auth())
        self.assertEqual(r.status_code, 200)
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.price, Decimal('9999.00'))

    def test_update_contract_logged(self):
        self.client.patch(f'/api/v1/contracts/{self.contract.pk}/',
                          data={'price': '7777.00'},
                          content_type='application/json',
                          HTTP_AUTHORIZATION=self._auth())
        log = ContractChangeLog.objects.filter(
            contract=self.contract, action='api:update').order_by('-id').first()
        self.assertIsNotNone(log)
        self.assertIn('price', log.details)

    def test_delete_contract(self):
        c = Contract.objects.create(
            project_site=self.site, contractor=self.contractor,
            name='del-contract', price=Decimal('100'), status='draft', stage='negotiation')
        r = self.client.delete(f'/api/v1/contracts/{c.pk}/',
                               HTTP_AUTHORIZATION=self._auth())
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Contract.objects.filter(pk=c.pk).exists())

    def test_delete_contract_logged(self):
        c = Contract.objects.create(
            project_site=self.site, contractor=self.contractor,
            name='del-log', price=Decimal('200'), status='draft', stage='negotiation')
        self.client.delete(f'/api/v1/contracts/{c.pk}/',
                           HTTP_AUTHORIZATION=self._auth())
        self.assertTrue(ContractChangeLog.objects.filter(
            action='api:delete', details__contains='del-log').exists())

    def test_unauthorized_write_401(self):
        r = self.client.post('/api/v1/contracts/', data={'name': 'x'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 401)

    def test_list_payments_by_contract(self):
        r = self.client.get(f'/api/v1/payments/?contract={self.contract.pk}')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], 'API-payment')

    def test_create_payment(self):
        r = self.client.post('/api/v1/payments/', data={
            'contract': self.contract.pk,
            'name': 'new-payment',
            'price': '800.00',
            'status': 'planned',
            'calc_type': 'manual',
        }, content_type='application/json',
           HTTP_AUTHORIZATION=self._auth())
        self.assertEqual(r.status_code, 201)
        self.assertTrue(ContractPayments.objects.filter(name='new-payment').exists())

    def test_patch_payment(self):
        r = self.client.patch(f'/api/v1/payments/{self.payment.pk}/',
                              data={'status': 'paid'},
                              content_type='application/json',
                              HTTP_AUTHORIZATION=self._auth())
        self.assertEqual(r.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')


class ImportPaymentsExcelTest(TestCase):
    """DMC-7: идемпотентный импорт платежей из Excel (openpyxl)."""

    @classmethod
    def setUpTestData(cls):
        cls.site = ProjectSite.objects.create(name='Excel-site')
        cls.contractor = Contractor.objects.create(name='Excel-contractor')
        cls.by_id = Contract.objects.create(
            project_site=cls.site, contractor=cls.contractor,
            name='Excel-by-id', number='EX-1', price=Decimal('10000.00'),
            status='active', stage='execution')
        cls.by_number = Contract.objects.create(
            project_site=cls.site, contractor=cls.contractor,
            name='Excel-by-num', number='EX-2', price=Decimal('20000.00'),
            status='active', stage='execution')

    def _build_xlsx(self, rows):
        import openpyxl
        import tempfile
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['contract_id', 'contract_number', 'name', 'price', 'status',
                   'due_date', 'calc_type', 'paid_amount', 'paid_date',
                   'invoice_number', 'payment_type', 'description'])
        for row in rows:
            ws.append(row)
        fd, path = tempfile.mkstemp(suffix='.xlsx')
        import os
        os.close(fd)
        wb.save(path)
        return path

    def _run(self, path, **kw):
        import io as _io
        from django.core.management import call_command
        out, err = _io.StringIO(), _io.StringIO()
        call_command('import_payments_excel', '--file', path, stdout=out, stderr=err, **kw)
        return out.getvalue(), err.getvalue()

    def test_import_creates(self):
        import os
        try:
            path = self._build_xlsx([
                [self.by_id.pk, '', 'п-от-id', '500.00', 'planned',
                 '2026-12-01', 'manual', '', '', '', 'advance', ''],
                ['', 'EX-2', 'п-от-number', '700.00', 'guaranteed',
                 '2026-12-05', 'manual', '', '', 'INV-7', 'final', ''],
            ])
            out, _ = self._run(path)
            self.assertIn('Создано: 2', out)
            self.assertEqual(ContractPayments.objects.filter(name='п-от-id').count(), 1)
            self.assertEqual(ContractPayments.objects.filter(name='п-от-number').count(), 1)
        finally:
            os.remove(path)

    def test_reimport_idempotent(self):
        import os
        try:
            path = self._build_xlsx([
                [self.by_id.pk, '', 'идемп', '500.00', 'planned', '2026-12-01',
                 'manual', '', '', '', 'advance', ''],
            ])
            self._run(path)
            n_before = ContractPayments.objects.count()
            out, _ = self._run(path)
            self.assertIn('Создано: 0', out)
            self.assertIn('обновлено: 1', out)
            self.assertEqual(ContractPayments.objects.count(), n_before)
        finally:
            os.remove(path)

    def test_dry_run_no_writes(self):
        import os
        try:
            path = self._build_xlsx([
                [self.by_id.pk, '', 'dry', '100.00', 'planned', '2026-12-01',
                 'manual', '', '', '', 'advance', ''],
            ])
            out, _ = self._run(path, **{'dry_run': True})
            self.assertIn('dry-run', out)
            self.assertEqual(ContractPayments.objects.filter(name='dry').count(), 0)
        finally:
            os.remove(path)

    def test_bad_contract_errors(self):
        import os
        from django.core.management import CommandError
        try:
            path = self._build_xlsx([
                [99999, '', 'badresp', '100.00', 'planned', '2026-12-01',
                 'manual', '', '', '', 'advance', ''],
            ])
            with self.assertRaises(CommandError):
                self._run(path)
            self.assertEqual(ContractPayments.objects.filter(name='badresp').count(), 0)
        finally:
            os.remove(path)

    def test_bad_status_skipped(self):
        import os
        from django.core.management import CommandError
        try:
            path = self._build_xlsx([
                [self.by_id.pk, '', 'bad-status', '100.00', 'nonexistent',
                 '2026-12-01', 'manual', '', '', '', 'advance', ''],
            ])
            with self.assertRaises(CommandError):
                self._run(path)
            self.assertEqual(ContractPayments.objects.filter(name='bad-status').count(), 0)
        finally:
            os.remove(path)

    def test_partial_update_amounts(self):
        import os
        try:
            ContractPayments.objects.create(
                contract=self.by_id, name='partial', calc_type='manual',
                price=Decimal('100'), status='planned',
                due_date=datetime.date(2026, 12, 1))
            path = self._build_xlsx([
                [self.by_id.pk, '', 'partial', '123.45', 'paid',
                 '2026-12-01', 'manual', '123.45', '2026-12-02', 'INV-1',
                 'advance', ''],
            ])
            out, _ = self._run(path)
            self.assertIn('обновлено: 1', out)
            p = ContractPayments.objects.get(name='partial')
            self.assertEqual(p.price, Decimal('123.45'))
            self.assertEqual(p.status, 'paid')
            self.assertEqual(p.invoice_number, 'INV-1')
        finally:
            os.remove(path)


class TaskChangeLogTest(TestCase):
    """DMX-1: аудит TaskNode в общем журнале ContractChangeLog (C4)."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User
        cls.user = User.objects.create_user('tasklog', 't@t.t', 'x')
        cls.site = ProjectSite.objects.create(name='TaskLog-site')
        cls.contractor = Contractor.objects.create(name='TaskLog-contractor')
        cls.contract = Contract.objects.create(
            project_site=cls.site, contractor=cls.contractor,
            name='TaskLog-договор', number='TL-1', price=Decimal('1000'))

    def _mk_task(self, **kw):
        from ProjectTDL.models import TaskNode
        kw.setdefault('name', 'лог-задача')
        kw.setdefault('owner', self.user)
        kw.setdefault('project_site', self.site)
        kw.setdefault('status', None)
        kw.setdefault('category', None)
        return TaskNode.objects.create(**kw)

    def test_create_logged_as_system_without_request(self):
        t = self._mk_task()
        e = ContractChangeLog.objects.filter(
            task=t, action='task:create').first()
        self.assertIsNotNone(e)
        self.assertIsNone(e.user)
        self.assertIsNone(e.contract)

    def test_create_with_contract_links_contract(self):
        t = self._mk_task(contract=self.contract)
        e = ContractChangeLog.objects.get(task=t, action='task:create')
        self.assertEqual(e.contract, self.contract)

    def test_create_via_view_logs_user(self):
        self.client.force_login(self.user)
        r = self.client.post('/quick_create_task/', {
            'name': 'вид-задача', 'project_site': self.site.pk})
        self.assertEqual(r.json()['status'], 'ok')
        e = ContractChangeLog.objects.get(action='task:create',
                                          details__contains='вид-задача')
        self.assertEqual(e.user, self.user)

    def test_update_via_view_logs_diff_with_user(self):
        t = self._mk_task()
        self.client.force_login(self.user)
        r = self.client.post('/update_task_field/', {
            'task_id': t.pk, 'field': 'price', 'value': '250.50'})
        self.assertEqual(r.json()['status'], 'ok')
        e = ContractChangeLog.objects.filter(
            task=t, action='task:update').order_by('-id').first()
        self.assertIsNotNone(e)
        self.assertEqual(e.user, self.user)
        self.assertIn('price', e.details)
        self.assertIn('250', e.details)

    def test_noop_save_writes_no_log(self):
        t = self._mk_task()
        n = ContractChangeLog.objects.filter(task=t).count()
        t.save()
        self.assertEqual(ContractChangeLog.objects.filter(task=t).count(), n)

    def test_delete_logged_entry_survives(self):
        t = self._mk_task()
        name = t.name
        t.delete()
        e = ContractChangeLog.objects.filter(
            action='task:delete', details__contains=name).first()
        self.assertIsNotNone(e)
        self.assertIsNone(e.task)  # SET_NULL — запись пережила задачу

    def test_bulk_update_single_summary(self):
        a = self._mk_task(name='bulk-a')
        b = self._mk_task(name='bulk-b')
        self.client.force_login(self.user)
        r = self.client.post('/bulk_update/', {
            'task_ids': [str(a.pk), str(b.pk)], 'price': '300'})
        self.assertEqual(r.json()['status'], 'ok')
        entries = ContractChangeLog.objects.filter(action='task:bulk_update')
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().user, self.user)
        self.assertIn('2', entries.first().details)

    def test_bulk_delete_logs_each(self):
        a = self._mk_task(name='del-a')
        b = self._mk_task(name='del-b')
        self.client.force_login(self.user)
        r = self.client.post('/bulk_delete/', {
            'task_ids': f'{a.pk},{b.pk}'})
        self.assertEqual(r.json()['status'], 'ok')
        self.assertEqual(
            ContractChangeLog.objects.filter(action='task:delete').count(), 2)

    def test_task_detail_shows_history_tab(self):
        t = self._mk_task()
        t.price = Decimal('500')
        t.save()
        self.client.force_login(self.user)
        r = self.client.get(f'/task/{t.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'История')
        self.assertContains(r, 'task:create')


class ContractReminderTest(TestCase):
    """DMX-2: ручные напоминания + команда check_reminders (C9)."""

    @classmethod
    def setUpTestData(cls):
        import datetime
        from django.contrib.auth.models import User
        from StaticData.models import Status
        cls.user = User.objects.create_user('remind', 'r@r.r', 'x')
        cls.site = ProjectSite.objects.create(name='Remind-site')
        cls.contractor = Contractor.objects.create(name='Remind-contractor')
        cls.contract = Contract.objects.create(
            project_site=cls.site, contractor=cls.contractor,
            name='Remind-договор', number='RM-1', price=Decimal('1000'))
        cls.status_open = Status.objects.create(name='Открыто')
        cls.status_closed = Status.objects.create(name='Закрыто')
        cls.today = datetime.date.today()
        cls.yesterday = cls.today - datetime.timedelta(days=1)

    def _mk_task(self, **kw):
        from ProjectTDL.models import TaskNode
        kw.setdefault('name', 'remind-задача')
        kw.setdefault('owner', self.user)
        kw.setdefault('project_site', self.site)
        kw.setdefault('category', None)
        return TaskNode.objects.create(**kw)

    def test_task_reminder_via_view(self):
        from ProjectContract.models import ContractReminder
        t = self._mk_task(contract=self.contract)
        self.client.force_login(self.user)
        r = self.client.post(f'/task/{t.pk}/remind/', {
            'due_date': self.today.isoformat(),
            'message': 'позвонить', 'recipient': self.user.pk})
        self.assertEqual(r.status_code, 302)
        rem = ContractReminder.objects.get(task=t)
        self.assertEqual(rem.contract, self.contract)
        self.assertEqual(rem.message, 'позвонить')
        self.assertEqual(rem.recipient, self.user)
        self.assertEqual(rem.created_by, self.user)
        self.assertFalse(rem.is_sent)
        self.assertTrue(ContractChangeLog.objects.filter(
            task=t, action='reminder:create').exists())

    def test_contract_reminder_via_view(self):
        from ProjectContract.models import ContractReminder
        self.client.force_login(self.user)
        r = self.client.post(f'/contract/{self.contract.pk}/remind/', {
            'due_date': self.today.isoformat(), 'message': 'шаг'})
        self.assertEqual(r.status_code, 302)
        rem = ContractReminder.objects.get(contract=self.contract,
                                           task__isnull=True)
        self.assertEqual(rem.message, 'шаг')
        self.assertTrue(ContractChangeLog.objects.filter(
            contract=self.contract, action='reminder:create').exists())

    def test_reminder_requires_date(self):
        from ProjectContract.models import ContractReminder
        t = self._mk_task()
        self.client.force_login(self.user)
        r = self.client.post(f'/task/{t.pk}/remind/', {'message': 'без даты'})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(ContractReminder.objects.filter(task=t).exists())

    def test_toggle_done(self):
        from ProjectContract.models import ContractReminder
        rem = ContractReminder.objects.create(
            contract=self.contract, due_date=self.today, message='t')
        self.client.force_login(self.user)
        self.client.post(f'/contract/reminder/{rem.pk}/toggle/')
        rem.refresh_from_db()
        self.assertTrue(rem.is_done)
        self.assertTrue(ContractChangeLog.objects.filter(
            contract=self.contract, action='reminder:done').exists())
        self.client.post(f'/contract/reminder/{rem.pk}/toggle/')
        rem.refresh_from_db()
        self.assertFalse(rem.is_done)

    def test_command_reports_overdue_sections(self):
        import io as _io
        from django.core.management import call_command
        from ProjectContract.models import ContractReminder
        from ProjectTDL.models import TaskNode
        ContractPayments.objects.create(
            contract=self.contract, name='пл-просрочен', calc_type='manual',
            price=Decimal('100'), status='planned', due_date=self.yesterday)
        ContractPayments.objects.create(
            contract=self.contract, name='пл-оплачен', calc_type='manual',
            price=Decimal('100'), status='paid', due_date=self.yesterday)
        self._mk_task(name='зад-просрочена', status=self.status_open,
                      due_date=self.yesterday)
        self._mk_task(name='зад-закрыта', status=self.status_closed,
                      due_date=self.yesterday)
        ContractReminder.objects.create(
            contract=self.contract, due_date=self.today, message='рук-текст')
        out = _io.StringIO()
        call_command('check_reminders', stdout=out)
        text = out.getvalue()
        self.assertIn('пл-просрочен', text)
        self.assertNotIn('пл-оплачен', text)
        self.assertIn('зад-просрочена', text)
        self.assertNotIn('зад-закрыта', text)
        self.assertIn('рук-текст', text)
        self.assertIn('ручные: 1, платежи: 1, задачи: 1', text)
        # без --mark-sent флаг не ставится
        self.assertFalse(
            ContractReminder.objects.get(message='рук-текст').is_sent)

    def test_command_mark_sent_and_done_excluded(self):
        import io as _io
        from django.core.management import call_command
        from ProjectContract.models import ContractReminder
        due = ContractReminder.objects.create(
            contract=self.contract, due_date=self.yesterday, message='к-отправке')
        ContractReminder.objects.create(
            contract=self.contract, due_date=self.yesterday,
            message='уже-закрыто', is_done=True)
        out = _io.StringIO()
        call_command('check_reminders', '--mark-sent', stdout=out)
        text = out.getvalue()
        self.assertIn('к-отправке', text)
        self.assertNotIn('уже-закрыто', text)
        due.refresh_from_db()
        self.assertTrue(due.is_sent)
        self.assertIsNotNone(due.sent_at)
        out2 = _io.StringIO()
        call_command('check_reminders', stdout=out2)
        self.assertIn('ручные: 0', out2.getvalue())


class TaskCommentTest(TestCase):
    """DMX-3: комментарии к задачам (C8)."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User
        from ProjectTDL.models import TaskNode
        cls.user = User.objects.create_user('commenter', 'c@c.c', 'x')
        cls.site = ProjectSite.objects.create(name='Comment-site')
        cls.contractor = Contractor.objects.create(name='Comment-contractor')
        cls.contract = Contract.objects.create(
            project_site=cls.site, contractor=cls.contractor,
            name='Comment-договор', number='CM-1', price=Decimal('1000'))
        cls.task = TaskNode.objects.create(
            name='comment-задача', owner=cls.user,
            project_site=cls.site, status=None, category=None,
            contract=cls.contract)

    def test_create_comment_via_view(self):
        from ProjectContract.models import TaskComment
        self.client.force_login(self.user)
        r = self.client.post(f'/task/{self.task.pk}/comment/', {
            'body': 'тестовый комментарий'})
        self.assertEqual(r.status_code, 302)
        c = TaskComment.objects.get(task=self.task)
        self.assertEqual(c.body, 'тестовый комментарий')
        self.assertEqual(c.author, self.user)

    def test_creates_contract_changelog(self):
        self.client.force_login(self.user)
        self.client.post(f'/task/{self.task.pk}/comment/', {
            'body': 'лог-коммент'})
        self.assertTrue(ContractChangeLog.objects.filter(
            task=self.task, action='task:comment',
            details='лог-коммент').exists())

    def test_empty_body_rejected(self):
        from ProjectContract.models import TaskComment
        self.client.force_login(self.user)
        r = self.client.post(f'/task/{self.task.pk}/comment/', {
            'body': ''})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(TaskComment.objects.filter(task=self.task).exists())

    def test_comment_visible_in_task_detail(self):
        from ProjectContract.models import TaskComment
        TaskComment.objects.create(task=self.task, author=self.user,
                                   body='виджет-текст')
        self.client.force_login(self.user)
        r = self.client.get(f'/task/{self.task.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Комментарии')
        self.assertContains(r, 'виджет-текст')

    def test_comment_list_ordering(self):
        from ProjectContract.models import TaskComment
        import datetime
        TaskComment.objects.create(task=self.task, author=self.user,
                                   body='первый')
        TaskComment.objects.create(task=self.task, author=self.user,
                                   body='второй')
        self.client.force_login(self.user)
        r = self.client.get(f'/task/{self.task.pk}/')
        body = r.content.decode()
        i1 = body.index('первый')
        i2 = body.index('второй')
        self.assertGreater(i1, i2, 'последний комментарий должен быть выше')


class TagAttachmentTest(TestCase):
    """DMX-4: теги (C10) + файлы (C11) на задачах/договорах."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User
        from ProjectTDL.models import TaskNode
        cls.user = User.objects.create_user('tagfile', 't@t.t', 'x')
        cls.site = ProjectSite.objects.create(name='TagFile-site')
        cls.contractor = Contractor.objects.create(name='TagFile-contractor')
        cls.contract = Contract.objects.create(
            project_site=cls.site, contractor=cls.contractor,
            name='TagFile-договор', number='TF-1', price=Decimal('1000'))
        cls.task = TaskNode.objects.create(
            name='tagfile-задача', owner=cls.user,
            project_site=cls.site, status=None, category=None,
            contract=cls.contract)
        cls.tag = Tag.objects.create(name='важное', color='#ff0000')

    def test_tag_assign_to_task(self):
        self.task.tags.add(self.tag)
        self.assertIn(self.tag, self.task.tags.all())

    def test_tag_assign_to_contract(self):
        self.contract.tags.add(self.tag)
        self.assertIn(self.tag, self.contract.tags.all())

    def test_task_attachment_upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from ProjectContract.models import Attachment
        self.client.force_login(self.user)
        f = SimpleUploadedFile('test.txt', b'hello')
        r = self.client.post(f'/task/{self.task.pk}/attach/', {
            'file': f, 'description': 'тестовый файл'})
        self.assertEqual(r.status_code, 302)
        a = Attachment.objects.get(task=self.task)
        self.assertEqual(a.uploaded_by, self.user)
        self.assertEqual(a.description, 'тестовый файл')
        self.assertTrue(ContractChangeLog.objects.filter(
            task=self.task, action='task:attach').exists())

    def test_contract_attachment_upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from ProjectContract.models import Attachment
        self.client.force_login(self.user)
        f = SimpleUploadedFile('contract.txt', b'data')
        r = self.client.post(f'/contract/{self.contract.pk}/attach/', {
            'file': f, 'description': 'дог-файл'})
        self.assertEqual(r.status_code, 302)
        a = Attachment.objects.get(contract=self.contract)
        self.assertEqual(a.uploaded_by, self.user)
        self.assertTrue(ContractChangeLog.objects.filter(
            contract=self.contract, action='contract:attach').exists())

    def test_empty_file_rejected(self):
        from ProjectContract.models import Attachment
        self.client.force_login(self.user)
        r = self.client.post(f'/task/{self.task.pk}/attach/', {})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Attachment.objects.filter(task=self.task).exists())

    def test_task_detail_shows_files_tab(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from ProjectContract.models import Attachment
        self.client.force_login(self.user)
        Attachment.objects.create(file=SimpleUploadedFile('vis.txt', b'x'),
                                  task=self.task, uploaded_by=self.user)
        r = self.client.get(f'/task/{self.task.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Файлы')

    def test_contract_docs_tab_shows_attachments(self):
        self.client.force_login(self.user)
        r = self.client.get(f'/contract/{self.contract.pk}/tab/docs/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Загрузить')


class ApplyChangesTest(TestCase):
    """EPIC-DJANGOCRM-API: idempotent apply_changes (JSON upsert-команда)."""

    @classmethod
    def setUpTestData(cls):
        cls.site = ProjectSite.objects.create(name='Apply-site')
        cls.contractor = Contractor.objects.create(name='Apply-contractor')
        cls.contract = Contract.objects.create(
            project_site=cls.site, contractor=cls.contractor,
            name='Apply-1', number='AP-1', price=Decimal('5000.00'),
            status='active', stage='execution')
        cls.payment = ContractPayments.objects.create(
            contract=cls.contract, name='apl-pay', calc_type='manual',
            price=Decimal('100'), status='planned',
            due_date=datetime.date(2026, 12, 15))

    def _run(self, payload, **kw):
        import io as _io
        import json
        import tempfile
        from django.core.management import call_command
        fd, path = tempfile.mkstemp(suffix='.json')
        import os
        os.close(fd)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh)
        out, err = _io.StringIO(), _io.StringIO()
        call_command('apply_changes', '--file', path, stdout=out, stderr=err, **kw)
        os.remove(path)
        return out.getvalue()

    def test_update_contract_and_payment(self):
        out = self._run({
            'contracts': [{'id': self.contract.pk, 'price': '8888.00',
                           'status': 'active'}],
            'payments': [{'contract_id': self.contract.pk, 'name': 'apl-pay',
                          'due_date': '2026-12-15', 'status': 'paid',
                          'invoice_number': 'INV-A'}],
        })
        self.assertIn('Applied: 2, errors: 0', out)
        self.contract.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.contract.price, Decimal('8888.00'))
        self.assertEqual(self.payment.status, 'paid')
        self.assertEqual(self.payment.invoice_number, 'INV-A')

    def test_missing_payment_skipped(self):
        from django.core.management import CommandError
        with self.assertRaises(CommandError):
            self._run({
                'payments': [{'contract_id': self.contract.pk,
                              'name': 'нет-такого', 'due_date': '2026-12-15',
                              'status': 'paid'}],
            })

    def test_dry_run_no_writes(self):
        out = self._run({
            'contracts': [{'id': self.contract.pk, 'price': '7777.00'}],
        }, **{'dry_run': True})
        self.assertIn('dry-run', out)
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.price, Decimal('5000.00'))
