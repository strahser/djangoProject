# -*- coding: utf-8 -*-
"""Блок 29 (B7): гарды фаз custom_task_view (ProjectTDL/services/task_view).

Пины факта до подмены view: разбор фильтров, персист сортировки (включая
мутацию request.GET), дерево-таблица, xlsx-экспорт, настройки (включая
отсутствие default_project_site в БД-ветке), дропдауны.
"""
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from ProjectTDL.models import TaskNode, TaskFilterState, UserSettings
from ProjectTDL.services import task_view as tv
from ProjectTDL.Tables import TaskNodeTable
from StaticData.models import Category, ProjectSite, Status


class TaskViewFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='b29_owner', password='pw')
        cls.site = ProjectSite.objects.create(name='Объект-Б29')
        cls.open = Status.objects.create(pk=1, name='Открыто')
        cls.category = Category.objects.create(pk=1, name='Проектная')
        cls.parent = TaskNode.objects.create(
            owner=cls.owner, project_site=cls.site, name='Родитель-Б29',
            status=cls.open, category=cls.category, price=100)
        cls.child = TaskNode.objects.create(
            owner=cls.owner, project_site=cls.site, parent=cls.parent,
            name='Дитя-Б29', status=cls.open, category=cls.category, price=50)


class ResolveListTest(TaskViewFixtureMixin, TestCase):
    def _get(self, user=None, **params):
        req = RequestFactory().get('/fake/', params)
        req.user = user if user is not None else self.owner
        return req

    def test_anon_get_sees_tasks(self):
        from django.contrib.auth.models import AnonymousUser
        resolved = tv.resolve_list_request(self._get(AnonymousUser()))
        pks = set(resolved['qs'].values_list('pk', flat=True))
        self.assertIn(self.parent.pk, pks)
        self.assertIn(self.child.pk, pks)
        self.assertEqual(resolved['initial'], {})

    def test_saved_state_prefills_initial(self):
        # FACT: params состояния — скаляры (save_filter_state пишет .get()).
        TaskFilterState.objects.create(
            user=self.owner, project_site=None,
            params={'status': str(self.open.pk), 'category': ''})
        resolved = tv.resolve_list_request(self._get())
        self.assertEqual(resolved['initial'], {'status': str(self.open.pk)})
        pks = set(resolved['qs'].values_list('pk', flat=True))
        self.assertIn(self.parent.pk, pks)


class ApplySortTest(TaskViewFixtureMixin, TestCase):
    def test_anon_get_mutated_to_minus_id(self):
        req = RequestFactory().get('/fake/')
        from django.contrib.auth.models import AnonymousUser
        req.user = AnonymousUser()
        tv.apply_table_sort(req)
        self.assertEqual(req.GET['sort'], '-id')

    def test_authed_url_sort_persisted(self):
        req = RequestFactory().get('/fake/', {'sort': 'name'})
        req.user = self.owner
        tv.apply_table_sort(req)
        self.assertEqual(
            UserSettings.objects.get(user=self.owner).table_sort, 'name')

    def test_authed_no_sort_reuses_saved(self):
        UserSettings.objects.create(user=self.owner, table_sort='name')
        req = RequestFactory().get('/fake/')
        req.user = self.owner
        tv.apply_table_sort(req)
        self.assertEqual(req.GET['sort'], 'name')


class BuildTableTest(TaskViewFixtureMixin, TestCase):
    def test_tree_mode_table(self):
        req = RequestFactory().get('/fake/', {'sort': '-id'})
        from django.contrib.auth.models import AnonymousUser
        req.user = AnonymousUser()
        resolved = tv.resolve_list_request(req)
        table, _qs = tv.build_task_table(req, resolved['qs'])
        self.assertIsInstance(table, TaskNodeTable)
        self.assertEqual(table.view_mode, 'tree')


class RootsDropdownsTest(TaskViewFixtureMixin, TestCase):
    def test_roots_only_parents(self):
        roots = tv.list_tree_roots()
        self.assertIn(self.parent, roots)
        self.assertNotIn(self.child, roots)

    def test_dropdowns_keys(self):
        dd = tv.filter_dropdowns()
        self.assertEqual(
            set(dd),
            {'all_contractors', 'all_statuses', 'all_categories',
             'all_project_sites', 'all_buildings', 'all_building_types',
             'all_design_chapters'})


class SettingsDictTest(TaskViewFixtureMixin, TestCase):
    def test_anon_defaults(self):
        from django.contrib.auth.models import AnonymousUser
        d = tv.user_settings_dict(AnonymousUser())
        self.assertFalse(d['inherit_props'])
        self.assertEqual(d['new_task_position'], 'bottom')
        self.assertTrue(d['auto_save'])

    def test_db_branch_has_no_default_project_site(self):
        # FACT: БД-ветка не возвращает default_project_site (дефолт False
        # из шапки недостижим для сохранённых). Пин факта, не идеала.
        UserSettings.objects.create(user=self.owner, table_sort='name')
        d = tv.user_settings_dict(self.owner)
        self.assertNotIn('default_project_site', d)
        self.assertEqual(d['table_sort'], 'name')


class ExportTest(TaskViewFixtureMixin, TestCase):
    def test_xlsx_response(self):
        req = RequestFactory().post('/fake/', {'save_attachments': '1'})
        req.user = self.owner
        req._messages = None
        from django.contrib.messages.storage.fallback import FallbackStorage
        req.session = self.client.session
        req._messages = FallbackStorage(req)
        resolved = tv.resolve_list_request(req)
        resp = tv.export_tasks_xlsx(req, resolved['qs'])
        self.assertEqual(
            resp['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        # FACT: кириллическое имя файла уходит RFC2047-encoded.
        from email.header import decode_header
        raw, enc = decode_header(resp['Content-Disposition'])[0]
        self.assertTrue(raw.decode(enc or 'utf-8').startswith('attachment'))
        self.assertTrue(len(resp.content) > 1000)


class CustomViewSmokeTest(TaskViewFixtureMixin, TestCase):
    def test_anon_get_200(self):
        resp = self.client.get(reverse('custom_task_view'))
        self.assertEqual(resp.status_code, 200)
