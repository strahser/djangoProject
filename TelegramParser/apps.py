import os
from django.apps import AppConfig


class TelegramparserConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'TelegramParser'
    verbose_name = 'Telegram Парсер'

    def ready(self):
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('DJANGO_AUTORELOAD'):
            from . import scheduled
            scheduled.start_telegram_scheduler()
