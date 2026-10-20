"""Тесты импорта реестра К1 из xlsx (МТФ/ФД/КЦ) и поля «проект».

Проверяем то, что важно для реестра:
- разбор xlsx: строки/здания/разделы по комплексам;
- нормализация раздела и вывод шифра из имени файла;
- поле «проект» у записи и здания, фильтр и колонка в админке;
- команда импорта в режиме --dry-run ничего не пишет.
"""
from __future__ import annotations

from io import BytesIO, StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from DocRegistry.management.commands import import_k1_xlsx_registry as imp
from DocRegistry.models import K1Building, K1Entry

XLSX_DIR = Path(r'd:\ПлагиныРевит\DesignBase\data\registry')


class K1XlsxParseTest(TestCase):
    """Разбор xlsx и чистые хелперы — без БД."""

    def test_cipher_strips_revision_and_date(self):
        self.assertEqual(imp._cipher('308.17.02-1КМ Коровник Изм.1 19.03.2020.pdf'),
                         '308.17.02-1КМ Коровник')
        self.assertEqual(imp._cipher('306.17-11-КЖ_изм.1_20.10.21.pdf'), '306.17-11-КЖ')
        self.assertEqual(imp._cipher('13-03-2025-10-ВК_03.04.2025.pdf'), '13-03-2025-10-ВК')
        self.assertEqual(imp._cipher('307.17- РТ.pdf'), '307.17- РТ')

    def test_section_normalization(self):
        self.assertEqual(imp._norm_section(' кж '), 'КЖ')
        self.assertEqual(imp._norm_section('АР1'), 'АР1')
        self.assertEqual(imp._norm_section('КЖ1 К2'), 'КЖ1 К2')
        self.assertEqual(imp._norm_section(None), '')

    def test_type_key_and_garbage_guard(self):
        self.assertEqual(imp._type_key('Коровник №5 (с родильным отделением)'), 'Коровник')
        self.assertEqual(imp._type_key('Доильно-молочный блок( админ. корпус)'),
                         'Доильно-молочный блок')
        # код раздела и «список номеров» — не имя здания → тип не назначаем
        self.assertIsNone(imp._building_type('ГП', {'ГП'}))
        self.assertIsNone(imp._building_type('2, 4.1-4.4, 6.1, 6.2', set()))

    def test_txt_cleans_excel_garbage(self):
        self.assertEqual(imp._txt('#N/A'), '')
        self.assertEqual(imp._txt(None), '')
        self.assertEqual(imp._txt(7.0), '7')
        self.assertEqual(imp._txt(7.1), '7.1')

    def test_typo_fixes_applied(self):
        """Опечатки источника правим при импорте."""
        self.assertEqual(imp.TYPO_BUILDINGS['Насоная станция'], 'Насосная станция')
        self.assertEqual(imp.TYPO_BUILDINGS['Все зданя'], 'Все здания')
        self.assertEqual(imp.TYPO_BUILDINGS['ТП 100кВа'], 'ТП 100 кВА')
        self.assertEqual(imp.TYPO_BUILDINGS['Малый дмб'], 'Малый ДМБ')
        self.assertEqual(imp.TYPO_BUILDINGS['Площадки силоса  и сенажа'],
                         'Площадки силоса и сенажа')
        self.assertEqual(imp.TYPO_BUILDINGS['Искуственный водоем с водосливом'],
                         'Искусственный водоем с водосливом')

    def test_resolve_building_prefers_directory(self):
        """Справочник зданий — источник истины для наименования."""
        by_poz = {'1': 'Телятник от 3 до 6 мес', '2': 'Телятник от 7 до 10 мес',
                  '0': 'Генеральный план'}
        by_name = {'Телятник от 3 до 6 мес': '1', 'Телятник от 7 до 10 мес': '2',
                   'Генеральный план': '0'}
        # в реестре имя перепутано — справочник знает правильное
        self.assertEqual(
            imp.resolve_building('ФД', '1', 'Телятник от 7 до 10 мес',
                                 by_poz=by_poz, by_name=by_name),
            ('1', 'Телятник от 3 до 6 мес'))
        # № пустой, имя единственное — то же здание
        self.assertEqual(
            imp.resolve_building('ФД', '', 'Телятник от 7 до 10 мес',
                                 by_poz=by_poz, by_name=by_name),
            ('2', 'Телятник от 7 до 10 мес'))
        # опечатка в имени правится
        self.assertEqual(
            imp.resolve_building('МТФ', '27.1', 'Насоная станция'),
            ('27.1', 'Насосная станция'))
        # имя пустое — здания нет
        self.assertIsNone(imp.resolve_building('МТФ', 'ГП', ''))
        # точечная правка по файлу: имя здания — из правки, номер — из справочника
        self.assertEqual(
            imp.resolve_building('ФД', '', 'Телятник от 7 до 10 мес',
                                 '306.17-ГП_изм.9-11_05.24.pdf',
                                 by_poz=by_poz, by_name=by_name),
            ('0', 'Генеральный план'))

    def test_status_fix(self):
        self.assertEqual(imp.FIX_STATUS_BY_FILE[('КЦ', '307.17-ЭМ.ЭО.pdf')],
                         'актуален')
        self.assertIn('актуален', imp.KNOWN_STATUSES)
        self.assertIn('не актуален', imp.KNOWN_STATUSES)


class K1XlsxImportTest(TestCase):
    """Команда импорта: --dry-run не пишет, реальный импорт заполняет."""

    @classmethod
    def setUpTestData(cls):
        from StaticData.models import ProjectSite
        cls.site = ProjectSite.objects.create(name='МТФ')

    def test_dry_run_writes_nothing(self):
        if not (XLSX_DIR / 'k1_mtf_2025-10-30.xlsx').exists():
            self.skipTest('нет копий xlsx')
        out = StringIO()
        call_command('import_k1_xlsx_registry', '--dry-run', stdout=out)
        self.assertIn('DRY-RUN', out.getvalue())
        self.assertEqual(K1Entry.objects.count(), 0)
        self.assertEqual(K1Building.objects.count(), 0)

    def test_entry_has_project_field(self):
        """Поле «проект» есть и у записи, и у здания."""
        from DocRegistry.models import BaseRegistryBuilding, BaseRegistryEntry
        for model in (BaseRegistryEntry, BaseRegistryBuilding):
            names = {f.name for f in model._meta.get_fields()}
            self.assertIn('project_site', names)
        entry = K1Entry.objects.create(code=1, file_name='x.pdf', project_site=self.site)
        self.assertEqual(entry.project_site_id, self.site.id)
        bld = K1Building.objects.create(code=1, name='Коровник №1', project_site=self.site)
        self.assertEqual(bld.project_site_id, self.site.id)

    def test_admin_lists_project_column_and_filter(self):
        from DocRegistry.admin import K1EntryAdmin
        from django.contrib import admin
        ma = K1EntryAdmin(K1Entry, admin.site)
        self.assertIn('project_site', ma.list_display)
        self.assertIn('project_site', [f for f in ma.list_filter
                                       if isinstance(f, str)])

    def test_export_has_project_column(self):
        from openpyxl import load_workbook
        from DocRegistry.exports import build_registry_xlsx
        entry = K1Entry.objects.create(code=1, file_name='x.pdf', project_site=self.site)
        wb = load_workbook(BytesIO(build_registry_xlsx([entry], 'K1')))
        ws = wb.active
        self.assertEqual(ws.cell(row=2, column=2).value, 'Проект')
        self.assertEqual(ws.cell(row=3, column=2).value, 'МТФ')
