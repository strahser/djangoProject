from django.apps import AppConfig


class ProjectcontractConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ProjectContract'
    verbose_name = 'Договоры'

    def ready(self):
        from . import signals  # noqa: F401 — регистрация пересчёта ДДС
