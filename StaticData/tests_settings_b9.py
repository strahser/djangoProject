# -*- coding: utf-8 -*-
"""Блок 9: тесты posture настроек (env-переопределения, DEBUG-гейты)."""
import os
from unittest.mock import patch

from django.conf import settings as dj_settings
from django.test import RequestFactory, TestCase, override_settings

from djangoProject.settings import _env_flag


class EnvFlagTest(TestCase):
    def test_true_false_default(self):
        with patch.dict(os.environ, {'X_FLAG': 'True'}):
            self.assertTrue(_env_flag('X_FLAG', False))
        with patch.dict(os.environ, {'X_FLAG': '0'}):
            self.assertFalse(_env_flag('X_FLAG', True))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('X_FLAG', None)
            self.assertTrue(_env_flag('X_FLAG', True))
            self.assertFalse(_env_flag('X_FLAG', False))

    def test_current_posture_documented(self):
        # Факт текущей установки: хосты не ограничены (раннер добавляет
        # 'testserver' сам — других быть не должно), пути продовые.
        # DEBUG в файле True (раннер тестов форсит False — его не проверяем).
        self.assertLessEqual(set(dj_settings.ALLOWED_HOSTS), {'testserver'})
        self.assertTrue(dj_settings.MEDIA_ROOT.endswith('Переписка'))
        self.assertTrue(dj_settings.SECRET_KEY)
        with patch.dict(os.environ, {'DJANGO_DEBUG': 'False'}):
            self.assertFalse(_env_flag('DJANGO_DEBUG', True))


class DevAutoLoginGateTest(TestCase):
    def _anon_request(self):
        from django.contrib.auth.models import AnonymousUser
        req = RequestFactory().get('/')
        req.user = AnonymousUser()
        return req

    def test_debug_off_does_nothing(self):
        # Гард: при DEBUG=False middleware не подменяет пользователя.
        from djangoProject.dev_autologin import DevAutoLoginMiddleware
        mw = DevAutoLoginMiddleware(lambda r: r)
        with override_settings(DEBUG=False):
            req = self._anon_request()
            self.assertIs(mw(req), req)
            self.assertFalse(req.user.is_authenticated)
