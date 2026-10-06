"""Блок 34: гарды сводки дня (djangoProject/dashboard)."""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from djangoProject.dashboard import dashboard_data
from Emails.models import Email
from ProjectContract.models import Contract, ContractPayments, Contractor
from ProjectTDL.models import TaskNode
from StaticData.models import Category, ProjectSite, Status


class DashboardDataTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='b34', password='pw')
        site = ProjectSite.objects.create(name='Объект-Б34')
        Status.objects.create(pk=1, name='Открыто')
        cls.closed = Status.objects.create(name='Закрыто')
        cls.open = Status.objects.get(pk=1)
        Category.objects.create(pk=1, name='Проектная')
        contractor = Contractor.objects.create(name='Подряд-Б34')
        cls.contract = Contract.objects.create(
            project_site=site, contractor=contractor,
            name='Договор-Б34', price=Decimal('100.00'))
        cls.site = site
        today = datetime.date.today()
        Email.objects.create(uid='b34-u1', subject='A', sender='a@t.co',
                             email_type='IN', folder='inbox',
                             sent_status='sent', is_read=False)
        Email.objects.create(uid='b34-u2', subject='B', sender='b@t.co',
                             email_type='IN', folder='inbox',
                             sent_status='sent', is_read=False)
        Email.objects.create(uid='b34-r', subject='C', sender='c@t.co',
                             email_type='IN', folder='inbox',
                             sent_status='sent', is_read=True)
        Email.objects.create(uid='b34-d', subject='D', sender='',
                             email_type='OUT', folder='drafts',
                             sent_status='draft')
        cls.overdue_open = TaskNode.objects.create(
            owner=cls.owner, project_site=site, name='Просрочка',
            status=cls.open,
            category=Category.objects.get(pk=1),
            due_date=today - datetime.timedelta(days=2))
        cls.overdue_closed = TaskNode.objects.create(
            owner=cls.owner, project_site=site, name='Закрытая просрочка',
            status=cls.closed,
            category=Category.objects.get(pk=1),
            due_date=today - datetime.timedelta(days=2))
        cls.upcoming = TaskNode.objects.create(
            owner=cls.owner, project_site=site, name='Скоро срок',
            status=cls.open,
            category=Category.objects.get(pk=1),
            due_date=today + datetime.timedelta(days=3))
        cls.pay = ContractPayments.objects.create(
            contract=cls.contract, name='Платёж-Б34', calc_type='manual',
            price=Decimal('10'), due_date=today + datetime.timedelta(days=5))
        ContractPayments.objects.create(
            contract=cls.contract, name='Оплачен', calc_type='manual',
            price=Decimal('20'), due_date=today + datetime.timedelta(days=5),
            made_payment=True, status='paid')

    def test_counts(self):
        data = dashboard_data()
        self.assertEqual(data['inbox_unread'], 2)
        self.assertEqual(data['drafts'], 1)

    def test_overdue_excludes_closed(self):
        data = dashboard_data()
        names = [t.name for t in data['overdue']]
        self.assertIn('Просрочка', names)
        self.assertNotIn('Закрытая просрочка', names)

    def test_due_week_and_payments(self):
        data = dashboard_data()
        self.assertIn('Скоро срок', [t.name for t in data['due_week']])
        self.assertEqual([p.name for p in data['payments']], ['Платёж-Б34'])
        self.assertEqual(data['payments_total'], Decimal('10'))

    def test_recent_inbox(self):
        data = dashboard_data()
        self.assertEqual(len(data['recent']), 3)
        subjects = [e.subject for e in data['recent']]
        self.assertIn('A', subjects)

    def test_page_renders(self):
        self.client.force_login(self.owner)
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Просрочка')
        self.assertNotContains(resp, 'Закрытая просрочка')

    def test_anonymous_redirected(self):
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.status_code, 302)
