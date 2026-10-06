# -*- coding: utf-8 -*-
"""F1: characterization-тесты ProjectTDL — фиксируют ФАКТ до рефакторинга.

Правило: тесты описывают текущее поведение, включая баги (пометка BUG).
После выноса логики в сервисы эти тесты — критерий «ничего не сломалось».
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ProjectTDL.models import TaskDueDateHistory, TaskNode
from ProjectTDL.Tables import TaskNodeTable
from ProjectTDL.views import _task_subtree_qs
from StaticData.models import Category, ProjectSite, Status


class GuardsFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='guard_owner', password='pw')
        cls.other = User.objects.create_user(username='guard_other', password='pw')
        cls.site = ProjectSite.objects.create(name='Объект-гарды')
        # TaskNode.status/category: FK default=1 — справочные строки pk=1 обязательны.
        cls.open = Status.objects.create(pk=1, name='Открыто')
        cls.closed = Status.objects.create(name='Закрыто')
        cls.category = Category.objects.create(pk=1, name='Проектная')
        cls.parent = TaskNode.objects.create(
            owner=cls.owner, project_site=cls.site, name='Родитель',
            status=cls.open, category=cls.category, price=100)
        cls.child = TaskNode.objects.create(
            owner=cls.owner, project_site=cls.site, parent=cls.parent,
            name='Дитя', status=cls.open, category=cls.category, price=50)


class CloneGuardsTest(GuardsFixtureMixin, TestCase):
    def test_task_clone_redirects_and_copies(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse('TaskCloneView', args=[self.parent.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(TaskNode.objects.filter(name='Родитель').count(), 2)

    def test_subtask_clone_without_referer_redirects(self):
        # Блок 8: без валидного HTTP_REFERER — редирект на список (был 500).
        self.client.force_login(self.owner)
        resp = self.client.get(reverse('SubTaskCloneView', args=[self.child.pk]))
        self.assertEqual(resp.status_code, 302)


class UpdateTaskFieldGuardsTest(GuardsFixtureMixin, TestCase):
    def _post(self, task_id, field, value):
        return self.client.post(
            reverse('update_task_field'),
            {'task_id': task_id, 'field': field, 'value': value})

    def test_price_dot_ok(self):
        self.client.force_login(self.owner)
        resp = self._post(self.parent.pk, 'price', '12.5')
        self.assertEqual(resp.json()['status'], 'ok')
        self.parent.refresh_from_db()
        self.assertEqual(str(self.parent.price), '12.50')

    def test_price_comma_ok(self):
        # Блок 8: одиночное обновление понимает запятую, как bulk.
        self.client.force_login(self.owner)
        resp = self._post(self.parent.pk, 'price', '12,34')
        self.assertEqual(resp.json()['status'], 'ok')
        self.parent.refresh_from_db()
        self.assertEqual(str(self.parent.price), '12.34')

    def test_other_users_task_rejected(self):
        # Блок 8: чужую задачу правит только владелец (было ok для всех).
        self.client.force_login(self.other)
        resp = self._post(self.parent.pk, 'name', 'Переименовано чужим')
        self.assertEqual(resp.json()['status'], 'error')
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.name, 'Родитель')

    def test_owner_can_edit(self):
        self.client.force_login(self.owner)
        resp = self._post(self.parent.pk, 'name', 'Новое имя')
        self.assertEqual(resp.json()['status'], 'ok')
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.name, 'Новое имя')

    def test_due_change_attributed_to_request_user(self):
        # Блок 8: история сроков пишется с request.user (был User.first()).
        self.client.force_login(self.owner)
        resp = self._post(self.parent.pk, 'due_date', '2030-05-01')
        self.assertEqual(resp.json()['status'], 'ok')
        row = TaskDueDateHistory.objects.get(task_node=self.parent)
        self.assertEqual(row.changed_by, self.owner)
        self.assertEqual(str(row.new_due_date), '2030-05-01')

    def test_unknown_field_rejected(self):
        resp = self._post(self.parent.pk, 'hacker_field', 'x')
        self.assertEqual(resp.json()['status'], 'error')

    def test_empty_name_rejected(self):
        resp = self._post(self.parent.pk, 'name', '   ')
        self.assertEqual(resp.json()['status'], 'error')


class BulkUpdateGuardsTest(GuardsFixtureMixin, TestCase):
    def test_bulk_price_comma_ok(self):
        # Факт: bulk понимает запятую (в отличие от update_task_field).
        self.client.force_login(self.owner)
        resp = self.client.post(reverse('bulk_update_tasks'), {
            'task_ids': [self.parent.pk, self.child.pk], 'price': '12,34'})
        self.assertEqual(resp.json()['status'], 'ok')
        self.parent.refresh_from_db()
        self.assertEqual(str(self.parent.price), '12.34')

    def test_bulk_skips_signals_no_due_history(self):
        # Факт: qs.update() не шлёт сигналов — TaskDueDateHistory не пишется,
        # только суммарный task:bulk_update в ContractChangeLog.
        from ProjectContract.models import ContractChangeLog
        self.client.force_login(self.owner)
        new_date = '2030-01-15'
        resp = self.client.post(reverse('bulk_update_tasks'), {
            'task_ids': [self.parent.pk], 'due_date': new_date})
        self.assertEqual(resp.json()['status'], 'ok')
        self.assertEqual(
            TaskDueDateHistory.objects.filter(task_node=self.parent).count(), 0)
        self.assertTrue(
            ContractChangeLog.objects.filter(action='task:bulk_update').exists())

    def test_bulk_empty_selection_rejected(self):
        self.client.force_login(self.owner)
        resp = self.client.post(reverse('bulk_update_tasks'), {})
        self.assertEqual(resp.json()['status'], 'error')


class SaveUserSettingsGuardsTest(GuardsFixtureMixin, TestCase):
    def test_invalid_json_silently_kept(self):
        # Факт: битый JSON в column_visibility молча игнорируется, status ok.
        self.client.force_login(self.owner)
        resp = self.client.post(reverse('save_user_settings'), {
            'column_visibility': '{битый json'})
        self.assertEqual(resp.json()['status'], 'ok')

    def test_bool_variants(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('save_user_settings'), {'inherit_props': 'on'})
        self.owner.task_user_settings.refresh_from_db()
        self.assertTrue(self.owner.task_user_settings.inherit_props)


class CustomTaskViewSortGuardsTest(GuardsFixtureMixin, TestCase):
    def test_url_sort_persisted_and_reused(self):
        # Факт: ?sort= запоминается в UserSettings и подставляется в GET,
        # когда sort не указан (views.py:150-165 мутирует request.GET).
        self.client.force_login(self.owner)
        resp = self.client.get(reverse('custom_task_view') + '?sort=name')
        self.assertEqual(resp.status_code, 200)
        self.owner.task_user_settings.refresh_from_db()
        self.assertEqual(self.owner.task_user_settings.table_sort, 'name')
        resp2 = self.client.get(reverse('custom_task_view'))
        self.assertEqual(resp2.status_code, 200)


class SubtreeQueryCountGuardTest(GuardsFixtureMixin, TestCase):
    def test_subtree_qs_query_count(self):
        # Гард перф-ловушки _task_subtree_qs (цикл bounds |= Q...).
        # Точное число ниже — факт на фикстуре 2 узла; рост = регрессия.
        with self.assertNumQueries(2):
            qs = _task_subtree_qs(
                {'status__id__in': [str(self.open.pk)]}, {})
            list(qs)


class TableNPlusOneGuardTest(GuardsFixtureMixin, TestCase):
    def _render_all(self, table, records):
        row_attrs_fn = TaskNodeTable.Meta.row_attrs['data-has-children']
        out = []
        for r in records:
            out.append((table.render_name(r), row_attrs_fn(r)))
        return out

    def test_annotated_zero_queries_per_row(self):
        # Блок 2: _task_subtree_qs аннотирует has_children_annotated —
        # рендер строк больше не бьёт в БД вообще.
        table = TaskNodeTable(_task_subtree_qs({}, {}))
        table.view_mode = 'tree'
        records = list(_task_subtree_qs({}, {}))
        self.assertEqual(len(records), 2)
        with self.assertNumQueries(0):
            rendered = self._render_all(table, records)
        by_name = {r.name: (html, flag) for r, (html, flag)
                   in zip(records, rendered)}
        self.assertEqual(by_name['Родитель'][1], '1')
        self.assertIn('fw-semibold', by_name['Родитель'][0])
        self.assertEqual(by_name['Дитя'][1], '0')
        self.assertNotIn('fw-semibold', by_name['Дитя'][0])

    def test_unannotated_fallback_still_works(self):
        # Фолбэк для таблиц вне _task_subtree_qs: legacy exists(), 2 запроса
        # на строку, но корректный результат.
        table = TaskNodeTable(TaskNode.objects.all())
        table.view_mode = 'tree'
        records = list(TaskNode.objects.all())
        with self.assertNumQueries(4):
            rendered = self._render_all(table, records)
        flags = sorted(flag for _, flag in rendered)
        self.assertEqual(flags, ['0', '1'])


class ExportXlsxGuardTest(GuardsFixtureMixin, TestCase):
    def test_save_attachments_returns_xlsx(self):
        self.client.force_login(self.owner)
        resp = self.client.post(reverse('custom_task_view'),
                                {'save_attachments': 'Экспорт в ексель'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        # Факт: не-ASCII имя «Задачи.xlsx» заставляет Django отдать весь
        # заголовок RFC2047-encoded.
        from email.header import decode_header
        raw, enc = decode_header(resp['Content-Disposition'])[0]
        decoded = raw.decode(enc or 'utf-8')
        self.assertIn('attachment', decoded)
        self.assertIn('Задачи.xlsx', decoded)
        self.assertTrue(resp.content[:2] == b'PK')  # zip-сигнатура xlsx
