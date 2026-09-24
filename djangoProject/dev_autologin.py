"""DEV ONLY: автоматический вход единственного пользователя.

Убирает запросы логина/пароля в локальной однопользовательской установке:
любой анонимный запрос обслуживается от имени DEV_AUTOLOGIN_USERNAME
(по умолчанию — первый активный superuser). Работает только при DEBUG=True;
в прод-режиме (DEBUG=False) middleware ничего не делает.

Примечание: пункт «Выйти» в админке после выхода тут же «входит» обратно —
это ожидаемо при включённом автологоне.
"""

from django.conf import settings
from django.contrib.auth import get_user_model


class DevAutoLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEBUG:
            user = getattr(request, 'user', None)
            if user is None or not user.is_authenticated:
                auto = self._dev_user()
                if auto is not None:
                    request.user = auto
        return self.get_response(request)

    @staticmethod
    def _dev_user():
        User = get_user_model()
        try:
            username = (getattr(settings, 'DEV_AUTOLOGIN_USERNAME', '') or '').strip()
            if username:
                return User.objects.filter(username=username, is_active=True).first()
            return User.objects.filter(is_superuser=True, is_active=True).order_by('id').first()
        except Exception:
            return None
