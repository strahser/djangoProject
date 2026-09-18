from django.apps import AppConfig


class DocregistryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'DocRegistry'
    verbose_name = 'Реестр документации'

    def ready(self):
        from django.contrib import admin

        from .admin_index import patch_admin_index
        patch_admin_index(admin.site)
