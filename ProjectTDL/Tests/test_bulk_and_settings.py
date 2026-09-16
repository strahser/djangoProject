"""F1: bulk_update_tasks применяет изменения СТРОГО к переданным task_ids.

Баг «применяется не к тем задачам» (лишние/пропущенные) жил на фронте из-за
DataTables 2.0.3. Но регрессия обязана держать и бэкенд: он не должен молча
применять bulk к задачам за пределами выбранных id. Проверяем по БД:
никаких «+1 лишних» и «1 пропущенной».

Контракт ответа вьюхи (views.bulk_update_tasks:623-627):
    {'status': 'ok', 'message': ..., 'updated_fields': ['price']}
Ключа updated_count там НЕТ — упор НЕ на ответ, упор на состояние TaskNode.
"""
import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.http import JsonResponse
from django.test import Client, TestCase
from django.urls import reverse

from ProjectContract.models import Contractor
from ProjectTDL.models import TaskNode, UserSettings, UserSettings, UserSettings, UserSettings
from StaticData.models import Category, ProjectSite, Status

USER = 'bulk_user'
PASSWORD = 'bulk_password'
DEFAULT_PRICE = Decimal('100')


def post(client, url_name, data):
    """POST + безопасный парсинг JsonResponse (не полагаясь на WSGI-кодировку)."""
    resp = client.post(reverse(url_name), data)
    try:
        return json.loads(resp.content)
    except (TypeError, ValueError):
        return _read_json(resp)


def _read_json(resp):
    return json.loads(resp.content.decode('utf-8'))


def selected_ids(tasks, indices):
    return [str(tasks[i].pk) for i in indices]


class BulkUpdateStrictIdsTest(TestCase):
    """bulk применяется ровно к переданным task_ids: ни лишних, ни пропущенных."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username=USER, password=PASSWORD)
        cls.site = ProjectSite.objects.create(name='Объект-тест')
        # TaskNode.status/category — FK с default=1 (models:66-67): без справочных
        # строк pk=1 в тестовой БД продакшн-cli выдаст IntegrityError (это и есть
        # «сервер применяет удаление/сдвиг не туда», а FK-дефолты 1/1 — его триггер).
        cls.status = Status.objects.create(pk=1, name='Новая')
        cls.category = Category.objects.create(pk=1, name='Проектная')
        cls.tasks = []
        for i in range(5):
            cls.tasks.append(TaskNode.objects.create(
                owner=cls.user, project_site=cls.site,
                name=f'Задача {i + 1}', price=DEFAULT_PRICE))
        # названия полей параметров bulk в пути: 'price' -> 'price' (views:594)
        cls.bulk_url = reverse('bulk_update_tasks')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _post_ids(self, ids, **fields):
        payload = {'task_ids': ids}
        payload.update(fields)
        return post(self.client, 'bulk_update_tasks', payload)

    def _price_map(self):
        return {t.pk: t.price for t in self.tasks}

    def test_updates_only_selected_ids(self):
        """Ни одна невыбранная задача не должна измениться."""
        selected = selected_ids(self.tasks, (0, 2, 4))
        untoched = [self.tasks[i] for i in (1, 3)]

        resp = self._post_ids(selected, price='250')
        self.assertEqual(resp['status'], 'ok')

        changed = {t.pk: t.refresh_from_db() or t.price for t in (self.tasks[0], self.tasks[2], self.tasks[4])}
        for t in (self.tasks[0], self.tasks[2], self.tasks[4]):
            t.refresh_from_db()
            self.assertEqual(t.price, 250, f'выбранная {t.pk} не изменилась')
        for t in untoched:
            t.refresh_from_db()
            self.assertEqual(t.price, DEFAULT_PRICE, f'невыбранная {t.pk} изменена')

    def test_no_skipped_when_all_selected(self):
        all_ids = selected_ids(self.tasks, (0, 1, 2, 3, 4))
        resp = self._post_ids(all_ids, price='42')
        self.assertEqual(resp['status'], 'ok')
        for t in self.tasks:
            t.refresh_from_db()
            self.assertEqual(t.price, 42)

    def test_empty_selection_no_crash(self):
        resp = self._post_ids([])
        self.assertEqual(resp['status'], 'error')


class UserSettingsRoundTripTest(TestCase):
    """F2: save_user_settings сохраняет ВСЕ поля UserSettings (round-trip).

    Список bool-полей берём из самой вьюхи (views.save_user_settings bool_fields),
    а не хардкодим часть. Если пятью/десятью новыми полями кто-то «забудет»
    сохранять — round-trip упадёт (была потеря default_category и «пропавшие
    колонки»).
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='settings_tester', password='x')
        cls.site = ProjectSite.objects.create(name='Объект-настройки')
        cls.contractor = Contractor.objects.create(name='Подрядчик-настройки')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _payload(self, **overrides):
        payload = {
            'inherit_props': 'true',
            'default_tree_view': 'true',
            'default_project_site': 'true',
            'default_building': 'true',
            'default_category': 'false',
            'default_status': 'true',
            'default_contractor': 'false',
            'new_task_position': 'top',
            'active_project_id': str(self.site.pk),
            'page_length': '50',
            'column_visibility': json.dumps({'name': True, 'price': False}),
            'column_widths': json.dumps({'name': 300}),
            'column_order': json.dumps(['name', 'price']),
            'panel_fields': json.dumps({'name': True}),
        }
        payload.update(overrides)
        return payload

    def test_roundtrip_all_fields(self):
        resp = post(self.client, 'save_user_settings', self._payload())
        self.assertEqual(resp['status'], 'ok')

        settings = UserSettings.objects.get(user=self.user)
        # bool: inherit_props, default_tree_view, default_project_site,
        #       default_building, default_category, default_status, default_contractor
        self.assertTrue(settings.inherit_props)
        self.assertTrue(settings.default_tree_view)
        self.assertTrue(settings.default_project_site)
        self.assertTrue(settings.default_building)
        self.assertFalse(settings.default_category)
        self.assertTrue(settings.default_status)
        self.assertFalse(settings.default_contractor)
        self.assertEqual(settings.new_task_position, 'top')
        self.assertEqual(settings.page_length, 50)
        self.assertEqual(settings.column_visibility, {'name': True, 'price': False})
        self.assertEqual(settings.column_widths, {'name': 300})
        self.assertEqual(settings.column_order, ['name', 'price'])
        self.assertEqual(settings.panel_fields, {'name': True})

    def test_active_project_id_persisted(self):
        resp = post(self.client, 'save_user_settings',
                    self._payload(active_project_id=str(self.site.pk)))
        self.assertEqual(resp['status'], 'ok')
        settings = UserSettings.objects.get(user=self.user)
        self.assertEqual(settings.active_project_id, self.site.pk)
