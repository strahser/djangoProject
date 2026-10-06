"""Блок 26: B3 (дубль декоратора draft_update снят) — auth-гард.

Дублированный @login_required/@require_http_methods был no-op, но маркером
copy-paste. Поведенческий пин: аноним всё так же редиректится на логин.
"""
from django.test import TestCase
from django.urls import reverse


class DraftUpdateAuthTest(TestCase):
    def test_anonymous_post_redirects_to_login(self):
        resp = self.client.post(
            reverse('email_ui:draft_update', args=[999999]), {})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp['Location'])

    def test_anonymous_get_rejected(self):
        resp = self.client.get(
            reverse('email_ui:draft_update', args=[999999]))
        self.assertEqual(resp.status_code, 302)
