# -*- coding: utf-8 -*-
"""Блок 17: гарды регистрации админок StaticData (без зависимости от ProjectTDL)."""
from django.apps import apps
from django.contrib import admin as dj_admin
from django.test import SimpleTestCase

from ProjectTDL import admin as tdl_admin  # noqa: F401 — импорт ради порядка
from StaticData import admin as static_admin


class AdminRegistryParityTest(SimpleTestCase):
    def test_all_staticdata_models_registered_once(self):
        static_models = set(apps.get_app_config('StaticData').get_models())
        registered = [m for m in static_models if m in dj_admin.site._registry]
        self.assertEqual(set(registered), static_models)

    def test_design_chapter_has_dedicated_admin(self):
        from ProjectTDL.admin import DesignChapterAdmin
        from StaticData.models import DesignChapter
        self.assertIsInstance(
            dj_admin.site._registry[DesignChapter], DesignChapterAdmin)

    def test_no_cross_admin_import(self):
        # StaticData/admin больше не тянет ProjectTDL/admin.
        import inspect
        imports = [ln.strip() for ln in
                   inspect.getsource(static_admin).splitlines()
                   if ln.strip().startswith(('from ', 'import '))]
        self.assertFalse(any('ProjectTDL' in ln for ln in imports),
                         imports)
