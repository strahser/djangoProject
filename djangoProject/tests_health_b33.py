"""Блок 33: гард health-пробы."""
from django.test import TestCase


class HealthzTest(TestCase):
    def test_ok_without_login(self):
        resp = self.client.get('/healthz/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'status': 'ok', 'db': 'ok'})
