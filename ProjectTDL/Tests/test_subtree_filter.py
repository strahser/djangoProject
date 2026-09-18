"""Фильтр задач: подзадача с явно чужим значением скрывается,
подзадача с пустым полем (наследование от родителя) остаётся.

Регрессия на жалобу «не отрабатывает фильтр по статусу»: _task_subtree_qs
возвращал подходящие задачи вместе со ВСЕМИ их подзадачами без фильтрации,
поэтому при фильтре «Открыто» в списке светились «Закрыто» подзадачи.
Правило наследования (_inherit_filter_q): пустое поле = «как у родителя»,
чужое значение = скрыть.
"""
from django.contrib.auth.models import User
from django.test import TestCase

from ProjectTDL.models import TaskNode
from ProjectTDL.views import _task_subtree_qs
from StaticData.models import Category, ProjectSite, Status


class SubtreeInheritFilterTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='filter_user', password='pw')
        cls.site = ProjectSite.objects.create(name='Объект-фильтр')
        # TaskNode.status/category — FK с default=1: справочные строки pk=1 обязательны.
        cls.open = Status.objects.create(pk=1, name='Открыто')
        cls.closed = Status.objects.create(name='Закрыто')
        cls.category = Category.objects.create(pk=1, name='Проектная')
        cls.parent = TaskNode.objects.create(
            owner=cls.user, project_site=cls.site,
            name='Родитель', status=cls.open, category=cls.category)
        cls.child_ok = TaskNode.objects.create(
            owner=cls.user, project_site=cls.site, parent=cls.parent,
            name='Дитя-совпадает', status=cls.open, category=cls.category)
        cls.child_bad = TaskNode.objects.create(
            owner=cls.user, project_site=cls.site, parent=cls.parent,
            name='Дитя-чужой-статус', status=cls.closed, category=cls.category)
        cls.child_empty = TaskNode.objects.create(
            owner=cls.user, project_site=cls.site, parent=cls.parent,
            name='Дитя-пустой-статус', status=None, category=cls.category)

    def _pks(self, qs):
        return set(qs.values_list('pk', flat=True))

    def test_foreign_status_hidden(self):
        qs = _task_subtree_qs({'status__id__in': [str(self.open.pk)]}, {})
        pks = self._pks(qs)
        self.assertIn(self.parent.pk, pks)
        self.assertIn(self.child_ok.pk, pks)
        self.assertNotIn(self.child_bad.pk, pks)

    def test_empty_status_inherits(self):
        qs = _task_subtree_qs({'status__id__in': [str(self.open.pk)]}, {})
        self.assertIn(self.child_empty.pk, self._pks(qs))

    def test_no_filter_returns_all(self):
        qs = _task_subtree_qs({}, {})
        pks = self._pks(qs)
        self.assertEqual(
            pks, {self.parent.pk, self.child_ok.pk, self.child_bad.pk, self.child_empty.pk})
