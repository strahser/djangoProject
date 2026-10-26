# -*- coding: utf-8 -*-
"""Перемещение задач в дереве (drag-and-drop): сервис move_task + вьюха task_move.

Открепить в корень (самостоятельная, node_type='task'); прикрепить —
дочерняя subtask. Циклы (сам в себя / в потомка) запрещены, чужие
задачи двигать нельзя (как в update_task_field — только владелец).
"""
from django.contrib.auth.models import User
from django.test import TestCase

from ProjectTDL.models import TaskNode
from ProjectTDL.services.task_mutations import indent_task, move_task, outdent_task
from StaticData.models import Category, ProjectSite, Status


class MoveTaskFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='mv_owner', password='pw')
        cls.other = User.objects.create_user(username='mv_other', password='pw')
        cls.site = ProjectSite.objects.create(name='MV-Объект')
        cls.open = Status.objects.create(name='Открыто')
        cls.category = Category.objects.create(name='Проектная')

    def _task(self, name, parent=None, owner=None):
        return TaskNode.objects.create(
            owner=owner or self.owner, project_site=self.site, name=name,
            status=self.open, category=self.category,
            node_type='subtask' if parent else 'task', parent=parent)


class MoveTaskServiceTest(MoveTaskFixtureMixin, TestCase):
    def test_detach_to_root(self):
        parent = self._task('P')
        child = self._task('C', parent=parent)
        result = move_task(child, None)
        self.assertTrue(result['ok'])
        child.refresh_from_db()
        self.assertIsNone(child.parent)
        self.assertEqual(child.node_type, 'task')
        parent.refresh_from_db()
        self.assertEqual(parent.get_children().count(), 0)

    def test_attach_as_subtask(self):
        p = self._task('P')
        t = self._task('T')
        result = move_task(t, p)
        self.assertTrue(result['ok'])
        t.refresh_from_db()
        self.assertEqual(t.parent, p)
        self.assertEqual(t.node_type, 'subtask')
        p.refresh_from_db()
        self.assertEqual(list(p.get_children()), [t])

    def test_self_move_rejected(self):
        t = self._task('T')
        result = move_task(t, t)
        self.assertFalse(result['ok'])
        t.refresh_from_db()
        self.assertIsNone(t.parent)

    def test_cycle_rejected(self):
        p = self._task('P')
        c = self._task('C', parent=p)
        g = self._task('G', parent=c)
        result = move_task(p, g)
        self.assertFalse(result['ok'])
        p.refresh_from_db()
        self.assertIsNone(p.parent)


class TaskMoveViewTest(MoveTaskFixtureMixin, TestCase):
    def _post(self, user, task_id, parent_id=''):
        self.client.force_login(user)
        return self.client.post('/task/move/', {
            'task_id': str(task_id), 'parent_id': str(parent_id or '')})

    def test_detach_via_view(self):
        p = self._task('P')
        c = self._task('C', parent=p)
        resp = self._post(self.owner, c.pk)
        self.assertEqual(resp.json()['status'], 'ok')
        self.assertIsNone(resp.json()['parent_id'])
        self.assertEqual(resp.json()['task_id'], c.pk)
        c.refresh_from_db()
        self.assertIsNone(c.parent)
        self.assertEqual(c.node_type, 'task')

    def test_attach_via_view(self):
        p = self._task('P')
        t = self._task('T')
        resp = self._post(self.owner, t.pk, p.pk)
        self.assertEqual(resp.json()['status'], 'ok')
        self.assertEqual(resp.json()['parent_id'], p.pk)
        t.refresh_from_db()
        self.assertEqual(t.parent, p)

    def test_cycle_via_view_rejected(self):
        p = self._task('P')
        c = self._task('C', parent=p)
        resp = self._post(self.owner, p.pk, c.pk)
        self.assertEqual(resp.json()['status'], 'error')
        p.refresh_from_db()
        self.assertIsNone(p.parent)

    def test_stranger_forbidden(self):
        p = self._task('P')
        c = self._task('C', parent=p)
        resp = self._post(self.other, c.pk)
        self.assertEqual(resp.json()['status'], 'error')
        c.refresh_from_db()
        self.assertEqual(c.parent, p)

    def test_missing_task_404(self):
        resp = self._post(self.owner, 999999)
        self.assertEqual(resp.status_code, 404)


class IndentOutdentTest(MoveTaskFixtureMixin, TestCase):
    def test_indent_under_previous_sibling(self):
        p = self._task('P')
        a = self._task('A', parent=p)
        b = self._task('B', parent=p)
        result = indent_task(b)
        self.assertTrue(result['ok'])
        b.refresh_from_db()
        self.assertEqual(b.parent, a)
        self.assertEqual(b.node_type, 'subtask')

    def test_indent_root_under_previous_root(self):
        a = self._task('A')
        b = self._task('B')
        result = indent_task(b)
        self.assertTrue(result['ok'])
        b.refresh_from_db()
        self.assertEqual(b.parent, a)

    def test_indent_first_child_rejected(self):
        p = self._task('P')
        a = self._task('A', parent=p)
        result = indent_task(a)
        self.assertFalse(result['ok'])
        a.refresh_from_db()
        self.assertEqual(a.parent, p)

    def test_outdent_to_grandparent(self):
        p = self._task('P')
        c = self._task('C', parent=p)
        g = self._task('G', parent=c)
        result = outdent_task(g)
        self.assertTrue(result['ok'])
        g.refresh_from_db()
        self.assertEqual(g.parent, p)
        self.assertEqual(g.node_type, 'subtask')

    def test_outdent_child_of_root_to_root(self):
        p = self._task('P')
        c = self._task('C', parent=p)
        result = outdent_task(c)
        self.assertTrue(result['ok'])
        c.refresh_from_db()
        self.assertIsNone(c.parent)
        self.assertEqual(c.node_type, 'task')

    def test_outdent_root_rejected(self):
        t = self._task('T')
        result = outdent_task(t)
        self.assertFalse(result['ok'])

    def test_modes_via_view(self):
        p = self._task('P')
        a = self._task('A', parent=p)
        b = self._task('B', parent=p)
        self.client.force_login(self.owner)
        resp = self.client.post('/task/move/', {
            'task_id': str(b.pk), 'mode': 'indent'})
        self.assertEqual(resp.json()['status'], 'ok')
        b.refresh_from_db()
        self.assertEqual(b.parent, a)
        resp = self.client.post('/task/move/', {
            'task_id': str(b.pk), 'mode': 'outdent'})
        self.assertEqual(resp.json()['status'], 'ok')
        b.refresh_from_db()
        self.assertEqual(b.parent, p)
        resp = self.client.post('/task/move/', {
            'task_id': str(p.pk), 'mode': 'outdent'})
        self.assertEqual(resp.json()['status'], 'error')
