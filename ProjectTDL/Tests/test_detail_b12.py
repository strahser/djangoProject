# -*- coding: utf-8 -*-
"""Блок 12: гарды карточки задачи (рендер, подзадачи без N+1)."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ProjectTDL.models import TaskNode
from StaticData.models import Category, ProjectSite, Status


class TaskDetailGuardsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='b12_owner', password='pw')
        cls.site = ProjectSite.objects.create(name='B12-Объект')
        cls.open = Status.objects.create(pk=1, name='Открыто')
        cls.category = Category.objects.create(pk=1, name='Проектная')
        cls.parent = TaskNode.objects.create(
            owner=cls.owner, project_site=cls.site, name='Карточка',
            status=cls.open, category=cls.category, price=Decimal('100'))
        for i in range(3):
            TaskNode.objects.create(
                owner=cls.owner, project_site=cls.site, parent=cls.parent,
                node_type='subtask', name=f'Подзадача {i}',
                status=cls.open, category=cls.category,
                price=Decimal('10'))

    def setUp(self):
        self.client.force_login(self.owner)

    def test_detail_renders_subtasks(self):
        resp = self.client.get(reverse('task_detail', args=[self.parent.pk]))
        self.assertEqual(resp.status_code, 200)
        for i in range(3):
            self.assertContains(resp, f'Подзадача {i}')
        self.assertContains(resp, 'Карточка')

    def test_detail_query_count(self):
        # Факт: карточка собирается ~10 одиночными запросами (сессия+юзер
        # тестового клиента сверху = 12), без N+1: шаблон подзадач трогает
        # только скаляры (pk/name/price/due_date/update_stamp), FK не ходит.
        # Проверено: select_related здесь не даёт дельты (откачено).
        # Рост числа = регрессия.
        with self.assertNumQueries(12):
            self.client.get(reverse('task_detail', args=[self.parent.pk]))
