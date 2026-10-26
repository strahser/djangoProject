# -*- coding: utf-8 -*-
"""Письмо → задача: одно действие создаёт задачу и прикрепляет письмо.

Раньше кнопка «Создать задачу» вела в админку на полную форму TaskNode:
связь письма терялась (в шаблоне админки не выводился _email_id), а задача
не появлялась в блоке «Задачи письма» (он читает email.tasks, а не
EmailTaskLink). Эти тесты фиксируют новое поведение.
"""
from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from Emails.models import Email
from email_ui.models import EmailRule, EmailTaskLink
from ProjectTDL.models import TaskNode, UserSettings
from StaticData.models import ProjectSite, Status, Category

User = get_user_model()


class _Base(TestCase):
    def setUp(self):
        super().setUp()
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        self.user = User.objects.create_superuser(
            'ssg_test', 'ssg@test.local', 'pw')
        self.project = ProjectSite.objects.create(name='Проект-1')
        self.email = Email.objects.create(
            uid='email-task-1',
            subject='Согласовать РД по объекту',
            sender='sender@test.local',
            project_site=self.project,
        )

    def _post(self, **extra):
        return self.client.post(
            reverse('email_ui:create_task_from_email', args=[self.email.pk]),
            **extra)


class EmailToTaskTest(_Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_post_creates_task_and_links_both_ways(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 302)

        task = TaskNode.objects.get()
        self.assertEqual(task.name, 'Согласовать РД по объекту')
        self.assertEqual(task.owner, self.user)
        self.assertEqual(task.project_site, self.project)
        self.assertEqual(task.node_type, 'task')

        # M2M — его читает блок «Задачи письма» на странице письма.
        self.assertIn(task, self.email.tasks.all())
        # EmailTaskLink — метаданные связи и админский inline.
        link = EmailTaskLink.objects.get()
        self.assertEqual(link.email, self.email)
        self.assertEqual(link.task_node, task)
        self.assertEqual(link.link_type, 'created_from')
        self.assertEqual(link.created_by, self.user)

    def test_name_is_truncated_to_model_limit(self):
        self.email.subject = 'Очень длинная тема ' * 30
        self.email.save(update_fields=['subject'])
        self._post()
        self.assertEqual(len(TaskNode.objects.get().name), 150)

    def test_project_falls_back_to_active_project(self):
        self.email.project_site = None
        self.email.save(update_fields=['project_site'])
        UserSettings.objects.create(user=self.user, active_project=self.project)

        self._post()
        self.assertEqual(TaskNode.objects.get().project_site, self.project)

    def test_without_project_no_task_and_warning(self):
        self.email.project_site = None
        self.email.save(update_fields=['project_site'])

        resp = self._post(follow=True)
        self.assertEqual(TaskNode.objects.count(), 0)
        self.assertEqual(EmailTaskLink.objects.count(), 0)
        self.assertContains(resp, 'не указан проект')

    def test_second_post_does_not_duplicate(self):
        self._post()
        self._post()
        self.assertEqual(TaskNode.objects.count(), 1)
        self.assertEqual(EmailTaskLink.objects.count(), 1)

    def test_htmx_returns_updated_block_and_toast(self):
        resp = self._post(HTTP_HX_REQUEST='true')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('Согласовать РД по объекту', body)
        self.assertIn('showToast', body)
        self.assertIn(f'email-tasks-count-{self.email.pk}', body)

    def test_get_is_not_allowed(self):
        resp = self.client.get(
            reverse('email_ui:create_task_from_email', args=[self.email.pk]))
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(TaskNode.objects.count(), 0)

    def test_detach_removes_both_links(self):
        self._post()
        task = TaskNode.objects.get()

        resp = self.client.post(
            reverse('email_ui:detach_task', args=[self.email.pk, task.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(task, self.email.tasks.all())
        self.assertEqual(EmailTaskLink.objects.count(), 0)


class EmailDetailTemplateTest(_Base):
    """Кнопка на странице письма — мгновенное создание, без админки."""

    def test_detail_page_has_instant_button(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse('email_ui:email_detail', args=[self.email.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        url = reverse('email_ui:create_task_from_email', args=[self.email.pk])
        self.assertIn(f'hx-post="{url}"', html)
        self.assertNotIn('tasknode_add', html)

    def test_inbox_modal_has_instant_button(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse('email_ui:email_detail_modal', args=[self.email.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        url = reverse('email_ui:create_task_from_email', args=[self.email.pk])
        self.assertIn(f'hx-post="{url}"', html)
        self.assertIn(f'id="email-tasks-body-{self.email.pk}"', html)

    def test_attach_page_has_instant_button(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse('email_ui:attach_tasks_page', args=[self.email.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        url = reverse('email_ui:create_task_from_email', args=[self.email.pk])
        self.assertIn(f'formaction="{url}"', html)
        self.assertNotIn('tasknode_add', html)


class RuleCreateTaskActionTest(_Base):
    """Действие правила create_task раньше логировало «Unknown action»."""

    def setUp(self):
        super().setUp()
        self.rule = EmailRule.objects.create(
            name='Письмо в задачу',
            conditions=[{'field': 'subject', 'operator': 'contains',
                         'value': 'РД'}],
            actions=[{'action': 'create_task', 'params': {}}],
            is_active=True,
        )

    def test_rule_creates_task_and_links_email(self):
        from email_ui.services.rule_engine import RuleEngine
        logs = RuleEngine().process_email(self.email)
        self.assertEqual(len(logs), 1)
        self.assertTrue(logs[0].success)
        self.assertIn('created', logs[0].action_taken)

        task = TaskNode.objects.get()
        self.assertEqual(task.name, 'Согласовать РД по объекту')
        # Владелец по умолчанию — первый активный суперпользователь.
        self.assertEqual(task.owner, self.user)
        self.assertIn(task, self.email.tasks.all())
        self.assertEqual(EmailTaskLink.objects.get().link_type, 'created_from')

    def test_second_run_does_not_duplicate(self):
        from email_ui.services.rule_engine import RuleEngine
        RuleEngine().process_email(self.email)
        RuleEngine().process_email(self.email)
        self.assertEqual(TaskNode.objects.count(), 1)
        self.assertEqual(EmailTaskLink.objects.count(), 1)

    def test_rule_without_project_reports_error(self):
        from email_ui.services.rule_engine import RuleEngine
        self.email.project_site = None
        self.email.save(update_fields=['project_site'])
        logs = RuleEngine().process_email(self.email)
        self.assertIn('error', logs[0].action_taken)
        self.assertEqual(TaskNode.objects.count(), 0)


class AdminOwnerChoicesTest(_Base):
    """Владелец задачи в админке — только суперпользователи (ssg)."""

    def setUp(self):
        super().setUp()
        self.plain = User.objects.create_user('plain_user', 'p@t.t', 'pw')
        self.client.force_login(self.user)

    def test_owner_select_has_no_plain_users(self):
        resp = self.client.get(reverse('admin:ProjectTDL_tasknode_add'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        import re
        match = re.search(r'<select[^>]*name="owner"[^>]*>(.*?)</select>',
                          html, re.S)
        self.assertIsNotNone(match, 'селект владельца не найден')
        options = match.group(1)
        self.assertIn(f'value="{self.user.pk}"', options)
        self.assertNotIn(f'value="{self.plain.pk}"', options)

    def test_admin_form_carries_email_hidden_field(self):
        resp = self.client.get(
            reverse('admin:ProjectTDL_tasknode_add')
            + f'?email_id={self.email.pk}&_next=/email/{self.email.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'name="_email_id" value="{self.email.pk}"')
        self.assertContains(resp, f'name="_next" value="/email/{self.email.pk}/"')

    def test_admin_save_model_links_email_m2m(self):
        from ProjectTDL.admin import TaskNodeAdmin

        model_admin = TaskNodeAdmin(TaskNode, django_admin.site)
        request = RequestFactory().post(
            '/admin/ProjectTDL/tasknode/add/',
            {'_email_id': str(self.email.pk)})
        request.user = self.user

        task = TaskNode(
            name='Из админки', owner=self.user, project_site=self.project)
        model_admin.save_model(request, task, form=None, change=False)

        self.assertIn(task, self.email.tasks.all())
        link = EmailTaskLink.objects.get()
        self.assertEqual(link.task_node, task)
        self.assertEqual(link.link_type, 'created_from')
