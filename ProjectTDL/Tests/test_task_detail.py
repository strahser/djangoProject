"""Карточка задачи: plain-text описания в списке, редактируемые
наименование/описание, привязка писем из вкладки «Письма» (DMX-5).
"""
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from Emails.models import Email
from ProjectTDL.models import TaskNode
from ProjectTDL.Tables import TaskNodeTable
from StaticData.models import Category, ProjectSite, Status


class TaskDetailTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='td_user', password='pw')
        cls.site = ProjectSite.objects.create(name='Объект-карточка')
        cls.status = Status.objects.create(pk=1, name='Открыто')
        cls.category = Category.objects.create(pk=1, name='Проектная')
        cls.task = TaskNode.objects.create(
            owner=cls.user, project_site=cls.site,
            name='Задача', description='<p>ТЭПы, <b>дороги</b></p>',
            status=cls.status, category=cls.category)
        cls.email = Email.objects.create(
            uid='td-mail-1', subject='По задаче', sender='a@t.com',
            receiver='b@t.com', email_type='IN', folder='inbox')

    def setUp(self):
        self.client.force_login(self.user)

    def test_render_description_strips_html(self):
        table = TaskNodeTable([])
        out = table.render_description(self.task)
        self.assertNotIn('<p>', out)
        self.assertNotIn('<b>', out)
        self.assertIn('ТЭПы', out)
        self.assertIn('дороги', out)

    def test_update_name_and_description(self):
        url = reverse('update_task_field')
        r = self.client.post(url, {'task_id': self.task.pk,
                                   'field': 'name', 'value': 'Новое имя'})
        self.assertEqual(json.loads(r.content)['status'], 'ok')
        r = self.client.post(url, {'task_id': self.task.pk,
                                   'field': 'description',
                                   'value': '<p>Новый текст</p>'})
        self.assertEqual(json.loads(r.content)['status'], 'ok')
        self.task.refresh_from_db()
        self.assertEqual(self.task.name, 'Новое имя')
        self.assertEqual(self.task.description, '<p>Новый текст</p>')

    def test_update_name_empty_rejected(self):
        url = reverse('update_task_field')
        r = self.client.post(url, {'task_id': self.task.pk,
                                   'field': 'name', 'value': '  '})
        self.assertEqual(json.loads(r.content)['status'], 'error')
        self.task.refresh_from_db()
        self.assertEqual(self.task.name, 'Задача')

    def test_task_detail_renders(self):
        r = self.client.get(reverse('task_detail', args=[self.task.pk]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn('id="td-name"', html)
        self.assertIn('id="td-description"', html)
        self.assertIn('id="btnNewSubtask"', html)
        self.assertIn('id="btnAttachEmail"', html)

    def test_email_candidates_and_attach_detach(self):
        cand_url = reverse('task_email_candidates', args=[self.task.pk])
        r = self.client.get(cand_url, {'q': 'задаче'})
        data = json.loads(r.content)
        self.assertEqual([e['id'] for e in data['emails']], [self.email.pk])

        attach_url = reverse('task_email_attach', args=[self.task.pk])
        r = self.client.post(attach_url, {'email_id': self.email.pk})
        self.assertEqual(r.status_code, 302)
        self.assertIn(self.email,
                      list(self.task.emails.all()))

        # Прикреплённое больше не предлагается кандидатом.
        r = self.client.get(cand_url, {'q': 'задаче'})
        self.assertEqual(json.loads(r.content)['emails'], [])

        detach_url = reverse('task_email_detach',
                             args=[self.task.pk, self.email.pk])
        r = self.client.post(detach_url)
        self.assertEqual(r.status_code, 302)
        self.assertNotIn(self.email, list(self.task.emails.all()))
