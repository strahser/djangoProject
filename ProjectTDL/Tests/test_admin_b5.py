# -*- coding: utf-8 -*-
"""Блок 5: тесты админки задач (отчёты, return-url, провенанс из письма)."""
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import TestCase

from Emails.models import Email
from ProjectTDL.admin import TaskNodeAdmin
from ProjectTDL.models import TaskNode
from ProjectTDL.services.admin_reports import build_admin_return_url
from email_ui.models import EmailTaskLink
from StaticData.models import Category, ProjectSite, Status


class AdminFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_superuser(
            username='b5_boss', password='pw', email='b@b.b')
        cls.owner = User.objects.create_user(username='b5_owner', password='pw')
        cls.site = ProjectSite.objects.create(name='B5-Объект')
        cls.open = Status.objects.create(pk=1, name='Открыто')
        cls.category = Category.objects.create(pk=1, name='Проектная')
        cls.task = TaskNode.objects.create(
            owner=cls.owner, project_site=cls.site, name='B5',
            status=cls.open, category=cls.category)

    def setUp(self):
        # ModelAdmin/RequestFactory — только в setUp: setUpTestData делает
        # deepcopy атрибутов, а ModelAdmin не копируется.
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        self.ma = TaskNodeAdmin(TaskNode, AdminSite())
        self.rf = RequestFactory()

    def _request(self, method='get', path='/', data=None, user=None):
        fn = getattr(self.rf, method)
        req = fn(path, data=data or {})
        req.user = user or self.boss
        req.session = {}
        req._messages = FallbackStorage(req)
        return req

    def _messages(self, request):
        return [str(m) for m in request._messages]

    def _post(self):
        return self._request(method='post', path='/')


class ReturnUrlTest(AdminFixtureMixin, TestCase):
    def test_filters_kept_service_dropped(self):
        req = self._request(
            path='/', data={'status__id__in': '2', '_popup': '1',
                            'action': 'x', 'q': ' baff '})
        url = build_admin_return_url(req, [self.task.pk])
        self.assertIn('status__id__in=2', url)
        self.assertIn(f'id__in={self.task.pk}', url)
        self.assertNotIn('_popup', url)
        self.assertNotIn('action=', url)
        self.assertTrue(url.startswith('http'))

    def test_no_params_no_query(self):
        req = self._request()
        url = build_admin_return_url(req)
        self.assertNotIn('?', url)

    def test_admin_wrapper_parity(self):
        req = self._request(data={'status__id__in': '2'})
        self.assertEqual(
            self.ma._get_admin_return_url(req, [self.task.pk]),
            build_admin_return_url(req, [self.task.pk]))


class ReportActionsTest(AdminFixtureMixin, TestCase):
    def test_html_empty_warns_none(self):
        req = self._post()
        resp = self.ma.generate_html_report(req, TaskNode.objects.none())
        self.assertIsNone(resp)
        self.assertTrue(any('ни одной задачи' in m for m in self._messages(req)))

    def test_protocol_empty_warns_none(self):
        req = self._post()
        resp = self.ma.generate_protocol_report(req, TaskNode.objects.none())
        self.assertIsNone(resp)
        self.assertTrue(any('ни одной задачи' in m for m in self._messages(req)))

    def test_html_report_file(self):
        req = self._post()
        resp = self.ma.generate_html_report(
            req, TaskNode.objects.filter(pk=self.task.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/html')
        self.assertIn('tasks_report.html', resp['Content-Disposition'])
        self.assertIn('B5', resp.content.decode('utf-8'))

    def test_protocol_file(self):
        req = self._post()
        resp = self.ma.generate_protocol_report(
            req, TaskNode.objects.filter(pk=self.task.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('protocol_soveshchaniya.html',
                      resp['Content-Disposition'])


class SaveModelProvenanceTest(AdminFixtureMixin, TestCase):
    def test_email_link_created(self):
        email = Email.objects.create(
            uid='b5-mail', sender='s@t.com', folder='inbox')
        req = self._request(method='post', path='/',
                            data={'_email_id': str(email.pk)})
        task = TaskNode.objects.create(
            owner=self.owner, project_site=self.site, name='FromMail',
            status=self.open, category=self.category)
        self.ma.save_model(req, task, form=None, change=False)
        self.assertTrue(EmailTaskLink.objects.filter(
            email=email, task_node=task,
            link_type='created_from').exists())

    def test_bad_email_id_no_crash_no_link(self):
        # Факт: битый _email_id больше не молчит — warning в лог, без исключения.
        req = self._request(method='post', path='/',
                            data={'_email_id': '999999'})
        task = TaskNode.objects.create(
            owner=self.owner, project_site=self.site, name='NoMail',
            status=self.open, category=self.category)
        with self.assertLogs('ProjectTDL.admin', level='WARNING'):
            self.ma.save_model(req, task, form=None, change=False)
        self.assertFalse(
            EmailTaskLink.objects.filter(task_node=task).exists())


class HtmlReplaceActionTest(AdminFixtureMixin, TestCase):
    def test_runs_without_exception(self):
        req = self._post()
        self.ma.html_replace(
            req, TaskNode.objects.filter(pk=self.task.pk))
        self.assertTrue(any('обновлены' in m for m in self._messages(req)))


class ChangelistSmokeTest(AdminFixtureMixin, TestCase):
    def test_changelist_renders(self):
        # Блок 23: smoke полного рендера (get_queryset + mptt + шаблоны).
        self.client.force_login(self.boss)
        resp = self.client.get('/admin/ProjectTDL/tasknode/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'B5')
