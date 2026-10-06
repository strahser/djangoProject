# -*- coding: utf-8 -*-
"""Блок 4: тесты сервисов ProjectTDL/services (фильтры + мутации).

Гарды F1/старого набора проверяют views сверху; здесь — контракты самих
сервисных функций (валидация, наследование, форматы ответов).
"""
from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase

from ProjectContract.models import ContractChangeLog
from ProjectTDL.models import TaskFilterState, TaskNode, UserSettings
from ProjectTDL.services.task_filters import (
    cascade_options,
    get_filter_state,
    inherit_filter_q,
    task_subtree_qs,
)
from ProjectTDL.services.task_mutations import (
    apply_bulk_update,
    create_task_with_defaults,
    parse_bulk_updates,
)
from StaticData.models import Category, ProjectSite, Status


class ServiceFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='b4_owner', password='pw')
        cls.site = ProjectSite.objects.create(name='B4-Объект')
        cls.open = Status.objects.create(pk=1, name='Открыто')
        cls.closed = Status.objects.create(name='Закрыто')
        cls.category = Category.objects.create(pk=1, name='Проектная')


class ParseBulkUpdatesTest(ServiceFixtureMixin, TestCase):
    def test_comma_price_and_int_fields(self):
        updates = parse_bulk_updates({'price': '12,34', 'status': '5'})
        self.assertEqual(updates, {'price': 12.34, 'status_id': 5})

    def test_invalid_silently_skipped(self):
        updates = parse_bulk_updates({'status': 'NaN', 'price': 'oops'})
        self.assertEqual(updates, {})

    def test_empty_and_unknown_ignored(self):
        updates = parse_bulk_updates(
            {'due_date': '', 'hacker': '1', 'price': '10'})
        self.assertEqual(updates, {'price': 10.0})

    def test_due_date_passthrough(self):
        updates = parse_bulk_updates({'due_date': '2030-01-15'})
        self.assertEqual(updates, {'due_date': '2030-01-15'})


class ApplyBulkUpdateTest(ServiceFixtureMixin, TestCase):
    def test_updates_and_single_audit_row(self):
        t = TaskNode.objects.create(
            owner=self.owner, project_site=self.site, name='T',
            status=self.open, category=self.category)
        result = apply_bulk_update([t.pk], {'status_id': self.closed.pk},
                                   self.owner)
        self.assertEqual(result['updated_count'], 1)
        self.assertEqual(result['ids'], [t.pk])
        self.assertEqual(result['updated_fields'], ['status_id'])
        t.refresh_from_db()
        self.assertEqual(t.status_id, self.closed.pk)
        self.assertEqual(ContractChangeLog.objects.filter(
            action='task:bulk_update').count(), 1)


class CreateTaskDefaultsTest(ServiceFixtureMixin, TestCase):
    def test_plain_create_without_settings(self):
        t = create_task_with_defaults(
            owner=self.owner, name='N', project_site_id=self.site.pk,
            status_id=self.open.pk)
        self.assertEqual(t.status_id, self.open.pk)
        self.assertEqual(t.owner, self.owner)

    def test_inherits_from_last_task(self):
        UserSettings.objects.create(user=self.owner, inherit_props=True)
        TaskNode.objects.create(
            owner=self.owner, project_site=self.site, name='Last',
            status=self.closed, category=self.category)
        t = create_task_with_defaults(
            owner=self.owner, name='New', project_site_id=self.site.pk)
        self.assertEqual(t.status_id, self.closed.pk)
        self.assertEqual(t.category_id, self.category.pk)

    def test_explicit_fields_win_over_inheritance(self):
        UserSettings.objects.create(user=self.owner, inherit_props=True)
        TaskNode.objects.create(
            owner=self.owner, project_site=self.site, name='Last',
            status=self.closed, category=self.category)
        t = create_task_with_defaults(
            owner=self.owner, name='New', project_site_id=self.site.pk,
            status_id=self.open.pk)
        self.assertEqual(t.status_id, self.open.pk)


class CascadeOptionsTest(ServiceFixtureMixin, TestCase):
    def test_empty_returns_all(self):
        opts = cascade_options()
        self.assertEqual(
            sorted(opts.keys()),
            ['buildings', 'categories', 'contractors', 'statuses'])
        self.assertTrue(any(s['name'] == 'Открыто' for s in opts['statuses']))

    def test_project_scoped_shape(self):
        TaskNode.objects.create(
            owner=self.owner, project_site=self.site, name='T',
            status=self.open, category=self.category)
        opts = cascade_options(project_site_id=self.site.pk)
        self.assertIn({'pk': self.open.pk, 'name': 'Открыто'},
                      opts['statuses'])


class GetFilterStateTest(ServiceFixtureMixin, TestCase):
    def test_anonymous_none(self):
        self.assertIsNone(get_filter_state(AnonymousUser()))

    def test_no_states_none(self):
        self.assertIsNone(get_filter_state(self.owner))

    def test_active_project_state_preferred(self):
        common = TaskFilterState.objects.create(
            user=self.owner, project_site=None, params={'a': '1'})
        proj = TaskFilterState.objects.create(
            user=self.owner, project_site=self.site, params={'b': '2'})
        UserSettings.objects.create(user=self.owner, active_project=self.site)
        self.assertEqual(get_filter_state(self.owner), proj)
        self.assertNotEqual(get_filter_state(self.owner), common)


class ServiceParityTest(ServiceFixtureMixin, TestCase):
    def test_subtree_qs_matches_views_wrapper(self):
        # Сервис и обёртка views возвращают одни и те же pk.
        from ProjectTDL.views import _task_subtree_qs as views_qs
        parent = TaskNode.objects.create(
            owner=self.owner, project_site=self.site, name='P',
            status=self.open, category=self.category)
        TaskNode.objects.create(
            owner=self.owner, project_site=self.site, parent=parent,
            name='C', status=self.open, category=self.category)
        filt = {'status__id__in': [str(self.open.pk)]}
        self.assertEqual(
            set(task_subtree_qs(filt, {}).values_list('pk', flat=True)),
            set(views_qs(filt, {}).values_list('pk', flat=True)))

    def test_inherit_q_wrapper_parity(self):
        from ProjectTDL.views import _inherit_filter_q as views_q
        filt = {'status__id__in': ['1']}
        TaskNode.objects.create(
            owner=self.owner, project_site=self.site, name='T',
            status=self.open, category=self.category)
        self.assertEqual(
            set(TaskNode.objects.filter(inherit_filter_q(filt, {}))
                .values_list('pk', flat=True)),
            set(TaskNode.objects.filter(views_q(filt, {}))
                .values_list('pk', flat=True)))


class DeleteReferenceTest(ServiceFixtureMixin, TestCase):
    """Блок 15: удаление справочников с защитой от каскадных потерь."""

    def _post_delete(self, model, obj_id):
        from django.test import Client
        c = Client()
        c.force_login(self.owner)
        return c.post('/manage_ref/', {'model': model, 'action': 'delete',
                                       'id': str(obj_id)})

    def test_used_status_blocked(self):
        from StaticData.models import Status
        TaskNode.objects.create(
            owner=self.owner, project_site=self.site, name='T',
            status=self.open, category=self.category)
        resp = self._post_delete('status', self.open.pk)
        self.assertEqual(resp.json()['status'], 'error')
        self.assertIn('TaskNode.status', resp.json()['message'])
        self.assertTrue(Status.objects.filter(pk=self.open.pk).exists())

    def test_unused_category_deleted(self):
        from StaticData.models import Category
        cat = Category.objects.create(name='Лишняя')
        resp = self._post_delete('category', cat.pk)
        self.assertEqual(resp.json()['status'], 'ok')
        self.assertFalse(Category.objects.filter(pk=cat.pk).exists())

    def test_contractor_with_tasks_and_contracts_blocked(self):
        from ProjectContract.models import Contract, Contractor
        from ProjectTDL.services.task_mutations import reference_usage
        contractor = Contractor.objects.create(name='Занятой')
        TaskNode.objects.create(
            owner=self.owner, project_site=self.site, name='T',
            status=self.open, category=self.category, contractor=contractor)
        Contract.objects.create(
            project_site=self.site, contractor=contractor, name='C',
            price=0)
        used = reference_usage('contractor', contractor.pk)
        self.assertEqual(
            sorted(f'{m}.{f}' for m, f, _ in used),
            ['ProjectContract.Contract.contractor',
             'ProjectTDL.TaskNode.contractor'])
        resp = self._post_delete('contractor', contractor.pk)
        self.assertEqual(resp.json()['status'], 'error')
        self.assertTrue(Contractor.objects.filter(pk=contractor.pk).exists())
        self.assertTrue(TaskNode.objects.filter(contractor=contractor).exists())

    def test_unknown_model_rejected(self):
        from django.test import Client
        c = Client()
        c.force_login(self.owner)
        resp = c.post('/manage_ref/', {'model': 'hacker', 'action': 'delete',
                                       'id': '1'})
        self.assertEqual(resp.json()['status'], 'error')
