# -*- coding: utf-8 -*-
"""Блок 6: тесты отчётов (форматтеры, due-матрица, протокол, счётчики запросов)."""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from Emails.models import Email
from ProjectTDL.models import TaskDueDateHistory, TaskNode
from ProjectTDL.reports import (
    ReportGenerator,
    _days_word,
    format_currency,
    html_convert,
)
from StaticData.models import Category, ProjectSite, Status


class ReportFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='b6_owner', password='pw')
        cls.site = ProjectSite.objects.create(name='B6-Объект')
        cls.open = Status.objects.create(pk=1, name='Открыто')
        cls.done = Status.objects.create(name='Выполнена')
        cls.category = Category.objects.create(pk=1, name='Проектная')
        cls.parent = TaskNode.objects.create(
            owner=cls.owner, project_site=cls.site, name='Родитель',
            status=cls.open, category=cls.category, price=Decimal('1000'),
            due_date=date(2026, 1, 1),
            description='<p>Решение: чинить</p>')
        cls.child = TaskNode.objects.create(
            owner=cls.owner, project_site=cls.site, parent=cls.parent,
            node_type='subtask', name='Дитя', status=cls.done,
            category=cls.category, due_date=date(2026, 1, 2))
        cls.email = Email.objects.create(
            uid='b6-mail', sender='s@t.com', subject='По задаче',
            folder='inbox', body_text='Согласовано, делаем')
        cls.email.tasks.add(cls.parent)
        TaskDueDateHistory.objects.create(
            task_node=cls.parent,
            old_due_date=date(2025, 12, 1), new_due_date=date(2026, 1, 1),
            changed_by=cls.owner)


class FormatCurrencyTest(TestCase):
    def test_none_zero(self):
        self.assertEqual(format_currency(None), '0.00')

    def test_grouping(self):
        self.assertEqual(format_currency(Decimal('1234567.89')), '1 234 567,89')

    def test_garbage_zero(self):
        # Факт: мусор глотается в 0.00 (предмет отдельного фикса).
        self.assertEqual(format_currency('мусор'), '0.00')

    def test_three_places(self):
        self.assertEqual(format_currency(10.5, 3), '10,500')


class DaysWordTest(TestCase):
    def test_matrix(self):
        self.assertEqual(
            [_days_word(n) for n in (1, 2, 5, 11, 14, 21, 22, 25)],
            ['день', 'дня', 'дней', 'дней', 'дней', 'день', 'дня', 'дней'])


class DueStateTest(TestCase):
    def test_matrix(self):
        today = date(2026, 6, 10)
        g = ReportGenerator._due_state
        self.assertEqual(g(None, False, today)[0], 'deadline-empty')
        self.assertEqual(g(date(2026, 6, 1), False, today)[1],
                         'просрочено на 9 дней')
        # Закрытая просрочка — нормальная дата, не «просрочено».
        self.assertEqual(g(date(2026, 6, 1), True, today)[0],
                         'deadline-normal')
        self.assertEqual(g(today, False, today)[0], 'deadline-today')
        self.assertEqual(g(date(2026, 6, 12), False, today)[0],
                         'deadline-soon')
        self.assertEqual(g(date(2026, 7, 10), False, today)[0],
                         'deadline-normal')


class ProtocolItemTest(ReportFixtureMixin, TestCase):
    def test_item_shape(self):
        item = ReportGenerator._protocol_item(
            self.parent, {self.parent.pk, self.child.pk},
            meeting_day=date(2026, 6, 10))
        self.assertEqual(item['depth'], 0)
        child_item = ReportGenerator._protocol_item(
            self.child, {self.parent.pk, self.child.pk},
            meeting_day=date(2026, 6, 10))
        self.assertEqual(child_item['depth'], 1)
        self.assertEqual(child_item['path'], ['Родитель'])
        self.assertEqual(item['path'], [])
        self.assertTrue(item['is_overdue'])
        self.assertFalse(item['is_closed'])
        self.assertEqual(len(item['subtasks']), 1)
        self.assertEqual(item['subtasks'][0]['name'], 'Дитя')
        self.assertTrue(item['subtasks'][0]['is_closed'])
        self.assertEqual(item['email_count'], 1)
        self.assertIn('Согласовано', item['emails'][0]['excerpt'])
        self.assertEqual(item['moves_count'], 1)
        self.assertEqual(item['last_move']['changed_by'], 'b6_owner')
        self.assertTrue(item['has_decision'])

    def test_item_query_count(self):
        # Гард N+1 протокола: предки + дети(+статус одним запросом) +
        # письма + история = 4. Было 5 до select_related('status').
        # Рост = регрессия.
        task = TaskNode.objects.select_related(
            'project_site', 'status', 'category').get(pk=self.parent.pk)
        with self.assertNumQueries(4):
            ReportGenerator._protocol_item(
                task, {self.parent.pk, self.child.pk}, date(2026, 6, 10))


class HtmlConvertTest(TestCase):
    def test_strips_tags(self):
        self.assertEqual(html_convert('<p>Hi <b>x</b></p>'), 'Hi x')

    def test_none_empty(self):
        self.assertEqual(html_convert(None), '')
        self.assertEqual(html_convert(''), '')


class CustomReportViewTest(ReportFixtureMixin, TestCase):
    def _get(self, **params):
        from django.test import Client
        c = Client()
        c.force_login(self.owner)
        return c.get('/reports/custom/', params)

    def test_no_ids_message(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Не выбраны задачи', resp.content.decode('utf-8'))

    def test_garbage_ids_message_not_500(self):
        # Блок 21: мусор отбрасывается вместо 500.
        resp = self._get(task_ids='abc,!!!')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Не выбраны задачи', resp.content.decode('utf-8'))

    def test_html_report_file(self):
        resp = self._get(task_ids=f'{self.parent.pk},{self.child.pk}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('custom_tasks_report.html',
                      resp['Content-Disposition'])
        self.assertIn('Родитель', resp.content.decode('utf-8'))

    def test_protocol_report_file(self):
        resp = self._get(task_ids=str(self.parent.pk), format='protocol')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('protocol_soveshchaniya.html',
                      resp['Content-Disposition'])

    def test_bad_meeting_date_falls_back(self):
        resp = self._get(task_ids=str(self.parent.pk), format='protocol',
                         meeting_date='не дата')
        self.assertEqual(resp.status_code, 200)
