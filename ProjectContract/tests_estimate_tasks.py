# -*- coding: utf-8 -*-
"""Создание задач из позиций сметы (экшен EstimateConceptAdmin).

Создаёт TaskNode из незакрытых (без акта) позиций: предзаполнение
проект/подрядчик/здание/раздел/договор/цена, связки EstimateTaskLink,
task_node — только первая (основная). Закрытые актом пропускаются.
"""
from decimal import Decimal

from django.contrib import admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from ProjectContract.admin import EstimateConceptAdmin
from ProjectContract.models import (
    Act, Contract, ContractEstimate, Contractor, EstimateConcept,
    EstimateTaskLink,
)
from ProjectTDL.models import TaskNode
from StaticData.models import (
    BuildingNumber, BuildingType, Category, DesignChapter, ProjectSite,
    Status,
)


class EstimateTaskActionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User
        cls.owner = User.objects.create_superuser(
            username='est_owner', password='pw', email='e@e.e')
        cls.site = ProjectSite.objects.create(name='ET-Объект')
        cls.contractor = Contractor.objects.create(name='ET-Подрядчик')
        cls.contract = Contract.objects.create(
            project_site=cls.site, contractor=cls.contractor,
            name='ET-Договор', price=Decimal('1000000.00'))
        cls.estimate = ContractEstimate.objects.create(
            contract=cls.contract, name='ET-Смета')
        cls.building = BuildingNumber.objects.create(
            name=BuildingType.objects.create(name='ET-Коровник'),
            building_number='3')
        cls.chapter = DesignChapter.objects.create(
            name='ET-Раздел', short_name='ET')
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        cls.open1 = EstimateConcept.objects.create(
            estimate=cls.estimate, name='Поз-1',
            building_number=cls.building, design_chapter=cls.chapter,
            amount=Decimal('15000.00'))
        cls.open2 = EstimateConcept.objects.create(
            estimate=cls.estimate, name='Поз-2',
            amount=Decimal('25000.00'))
        cls.act = Act.objects.create(
            number='7', contract=cls.contract)
        cls.closed = EstimateConcept.objects.create(
            estimate=cls.estimate, name='Поз-закрытая',
            amount=Decimal('5000.00'), act=cls.act)

    def _apply(self, ids, group=False):
        ma = EstimateConceptAdmin(EstimateConcept, admin.site)
        rf = RequestFactory()
        data = {
            'action': 'create_tasks_from_concepts',
            'apply': '1',
            '_selected_action': [str(i) for i in ids],
        }
        if group:
            data['group_by_contract'] = '1'
        request = rf.post('/admin/', data=data)
        request.user = self.owner
        request.session = {}
        request._messages = FallbackStorage(request)
        qs = EstimateConcept.objects.filter(pk__in=ids)
        return ma.create_tasks_from_concepts(request, qs)

    def test_creates_flat_tasks_by_default(self):
        """По умолчанию (без галочки) — плоские корневые задачи, без родителя."""
        resp = self._apply([self.open1.pk, self.open2.pk])
        self.assertEqual(resp.status_code, 302)
        t1 = TaskNode.objects.get(
            estimate_links__estimate_concept=self.open1)
        self.assertEqual(t1.name, 'Поз-1')
        self.assertEqual(t1.price, Decimal('15000.00'))
        self.assertEqual(t1.project_site, self.site)
        self.assertEqual(t1.contractor, self.contractor)
        self.assertEqual(t1.building_number, self.building)
        self.assertEqual(t1.design_chapter, self.chapter)
        self.assertEqual(t1.contract, self.contract)
        self.assertIsNone(t1.due_date)
        self.assertEqual(t1.node_type, 'task')
        self.assertIsNone(t1.parent)
        self.assertFalse(TaskNode.objects.filter(
            name='ET-Договор — работы по смете').exists())
        link = EstimateTaskLink.objects.get(
            estimate_concept=self.open1, task_node=t1)
        self.assertEqual(link.link_type, 'created_from')
        self.assertEqual(link.created_by, self.owner)
        self.open1.refresh_from_db()
        self.assertEqual(self.open1.task_node, t1)

    def test_grouped_creates_parent_and_children(self):
        resp = self._apply([self.open1.pk, self.open2.pk], group=True)
        self.assertEqual(resp.status_code, 302)
        t1 = TaskNode.objects.get(
            estimate_links__estimate_concept=self.open1)
        self.assertEqual(t1.node_type, 'subtask')
        parent = t1.parent
        self.assertIsNotNone(parent)
        self.assertEqual(parent.node_type, 'task')
        self.assertIsNone(parent.parent)
        self.assertEqual(parent.name, 'ET-Договор — работы по смете')
        self.assertEqual(parent.contract, self.contract)
        t2 = TaskNode.objects.get(
            estimate_links__estimate_concept=self.open2)
        self.assertEqual(t2.parent, parent)
        parent.refresh_from_db()
        self.assertEqual(parent.price, Decimal('40000.00'))

    def test_skips_closed(self):
        n_before = TaskNode.objects.count()
        self._apply([self.closed.pk])
        self.assertEqual(TaskNode.objects.count(), n_before)
        self.assertFalse(EstimateTaskLink.objects.filter(
            estimate_concept=self.closed).exists())

    def test_second_run_skips_linked(self):
        # Повтор по привязанной позиции ничего не создаёт (раньше плодил
        # вторую связку) — «которых нет сейчас».
        self._apply([self.open2.pk])
        first = EstimateConcept.objects.get(pk=self.open2.pk).task_node
        self.assertIsNotNone(first)
        n_tasks = TaskNode.objects.count()
        n_links = EstimateTaskLink.objects.filter(
            estimate_concept=self.open2).count()
        self._apply([self.open2.pk])
        self.open2.refresh_from_db()
        self.assertEqual(self.open2.task_node, first)
        self.assertEqual(TaskNode.objects.count(), n_tasks)
        self.assertEqual(
            EstimateTaskLink.objects.filter(
                estimate_concept=self.open2).count(), n_links)

    def test_two_contracts_two_parents(self):
        contract2 = Contract.objects.create(
            project_site=self.site, contractor=self.contractor,
            name='ET-Договор-2', price=Decimal('500000.00'))
        estimate2 = ContractEstimate.objects.create(
            contract=contract2, name='ЕТ-Смета-2')
        other = EstimateConcept.objects.create(
            estimate=estimate2, name='Поз-чужая',
            amount=Decimal('7000.00'))
        self._apply([self.open1.pk, other.pk], group=True)
        p1 = TaskNode.objects.get(
            estimate_links__estimate_concept=self.open1).parent
        p2 = TaskNode.objects.get(
            estimate_links__estimate_concept=other).parent
        self.assertNotEqual(p1.pk, p2.pk)
        self.assertEqual(p1.name, 'ET-Договор — работы по смете')
        self.assertEqual(p2.name, 'ET-Договор-2 — работы по смете')
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.price, Decimal('15000.00'))
        self.assertEqual(p2.price, Decimal('7000.00'))

    def test_parent_reused_on_rerun(self):
        self._apply([self.open1.pk], group=True)
        parent = TaskNode.objects.get(
            estimate_links__estimate_concept=self.open1).parent
        n_parents = TaskNode.objects.filter(parent__isnull=True).count()
        self._apply([self.open2.pk], group=True)
        parent.refresh_from_db()
        self.assertEqual(TaskNode.objects.filter(parent__isnull=True).count(),
                         n_parents)
        self.assertEqual(
            TaskNode.objects.get(
                estimate_links__estimate_concept=self.open2).parent, parent)
        self.assertEqual(parent.price, Decimal('40000.00'))

    def test_confirm_page_lists_positions(self):
        ma = EstimateConceptAdmin(EstimateConcept, admin.site)
        rf = RequestFactory()
        request = rf.post('/admin/', data={
            'action': 'create_tasks_from_concepts',
            '_selected_action': [str(self.open1.pk), str(self.closed.pk)],
        })
        request.user = self.owner
        qs = EstimateConcept.objects.filter(
            pk__in=[self.open1.pk, self.closed.pk])
        resp = ma.create_tasks_from_concepts(request, qs)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('Поз-1', body)
        self.assertIn('пропуск', body)
        self.assertIn('ET-Договор — работы по смете', body)
        # опция группировки по умолчанию выключена
        self.assertIn('name="group_by_contract"', body)
        self.assertNotIn('group_by_contract" value="1" checked', body)

    def test_confirm_page_marks_linked(self):
        self._apply([self.open1.pk])
        ma = EstimateConceptAdmin(EstimateConcept, admin.site)
        rf = RequestFactory()
        request = rf.post('/admin/', data={
            'action': 'create_tasks_from_concepts',
            '_selected_action': [str(self.open1.pk)],
        })
        request.user = self.owner
        qs = EstimateConcept.objects.filter(pk=self.open1.pk)
        resp = ma.create_tasks_from_concepts(request, qs)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('есть задачи', body)
