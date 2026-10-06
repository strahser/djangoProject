# -*- coding: utf-8 -*-
"""F4: characterization-тесты DocRegistry — фиксируют ФАКТ до рефакторинга.

PDF без шрифтов Windows, dry-run импорта без живого accdb,
недоступность DesignBase. Не дублируют существующие PDF/flow-тесты.
"""
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from .models import (
    DocDeveloper,
    DocSection,
    M1Building,
    M1Entry,
    M1Remark,
    M1Revision,
)


class PdfNoArialTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.b = M1Building.objects.create(code=4, number='1.4', name='Коровник № 4')
        cls.s = DocSection.objects.create(code=21, short='ВК', name='ВиК')
        cls.d = DocDeveloper.objects.create(code=1, name='ДеЛаваль')
        e = M1Entry.objects.create(
            code=77, cipher='ВВ-17-1.4-КЖ1', section=cls.s,
            building_no=cls.b, building=cls.b, developer=cls.d)
        rev = M1Revision.objects.create(entry=e, rev_no=1, status='has_remarks')
        cls.rm = M1Remark.objects.create(revision=rev, text='Ось Б смещена')

    def test_styles_fallback_without_arial(self):
        # Факт: без arial.ttf _styles() молча откатывается на Helvetica.
        from .pdf_forms import _styles
        with patch('DocRegistry.pdf_forms.TTFont', side_effect=OSError('no font')):
            s = _styles()
        self.assertEqual(s['n'].fontName, 'Helvetica')

    def test_remark_sheet_builds_without_arial(self):
        # Факт: PDF строится и без Arial (кириллица на Helvetica —
        # предмет отдельного фикса шрифтов, здесь только «не падает»).
        from .pdf_forms import remark_sheet_bytes
        with patch('DocRegistry.pdf_forms.TTFont', side_effect=OSError('no font')):
            pdf = remark_sheet_bytes(self.rm)
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_signature_missing_returns_none(self):
        from .pdf_forms import _signature_image
        with patch('DocRegistry.pdf_forms.SIGNATURE_PNG', '/nonexistent/x.png'):
            self.assertIsNone(_signature_image({}))


class ImportDryRunGuardsTest(TestCase):
    def test_k1_without_accdb_path_fails(self):
        # Факт: путь K1.accdb неизвестен — без --accdb даже dry-run невозможен.
        from .accdb import resolve_path
        with self.assertRaises(ValueError):
            resolve_path('K1')

    def test_k1_dry_run_without_accdb_is_command_error(self):
        # Факт: dry-run всё равно требует живой accdb (resolve до чтения).
        with self.assertRaises(CommandError):
            call_command('import_accdb_registry', project='K1', dry_run=True)

    def test_m1_path_hardcoded(self):
        # Факт: путь M1 захардкожен на диск E: (не переносимо).
        from .accdb import resolve_path
        self.assertTrue(resolve_path('M1').startswith('E:'))


class DesignBaseUnreachableTest(TestCase):
    @override_settings(DESIGNBASE_URL='http://127.0.0.1:9')
    def test_call_closed_port_raises_unreachable(self):
        # Факт: недоступность маппится в DesignBaseUnreachable, не в URLError.
        # Порт 9 (discard) закрыт — отказ быстрый, сети не нужно.
        from .designbase_client import DesignBaseUnreachable, call, get, post
        with self.assertRaises(DesignBaseUnreachable):
            call('/health', timeout=1)
        with self.assertRaises(DesignBaseUnreachable):
            get('/health', params={'a': '1'}, timeout=1)
        with self.assertRaises(DesignBaseUnreachable):
            post('/validate', payload={'x': 1}, timeout=1)


class CompareRegistryTest(TestCase):
    """Блок 22: матрица сверки drift (чистая функция, без accdb/БД)."""

    def test_all_match_ok(self):
        from .services import compare_registry
        rows = [{'code': 1, 'accdb_row_hash': 'a'},
                {'code': 2, 'accdb_row_hash': 'b'}]
        rep = compare_registry(rows, {1: 'a', 2: 'b'})
        self.assertTrue(rep['ok'])
        self.assertEqual(rep, {'new': [], 'missing': [], 'changed': [],
                               'ok': True})

    def test_new_missing_changed(self):
        from .services import compare_registry
        rows = [{'code': 1, 'accdb_row_hash': 'a2'},
                {'code': 3, 'accdb_row_hash': 'c'}]
        rep = compare_registry(rows, {1: 'a', 2: 'b'})
        self.assertFalse(rep['ok'])
        self.assertEqual(rep['new'], [3])
        self.assertEqual(rep['missing'], [2])
        self.assertEqual(rep['changed'], [1])

    def test_empty_live_all_missing(self):
        from .services import compare_registry
        rep = compare_registry([], {1: 'a'})
        self.assertEqual(rep['missing'], [1])
        self.assertFalse(rep['ok'])
