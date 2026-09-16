"""F3: регрессия версии вендора DataTables.

Причина багов «bulk не к тем задачам», «колонки пропадали из настроек» и
«нет переноса наименования» — DataTables 2.0.3 падал при scrollX в applyColumnOrder.
Вендор откачен на 1.13.8. Тест держит версию: если кто-то снова подтянет 2.x —
он честно упадёт.
"""
import os
import re

from django.conf import settings
from django.test import SimpleTestCase


class DataTablesVendorRegressionTest(SimpleTestCase):
    DATA = 'DataTables'

    def _read_vendor(self, filename):
        base = getattr(settings, 'STATICFILES_DIRS', [])
        root = base[0] if base else os.path.dirname(settings.BASE_DIR)
        path = os.path.join(root, self.DATA, filename)
        self.assertTrue(os.path.isfile(path), f'не найден вендор: {path}')
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            return fh.read()

    def test_datatables_is_1_13_x_not_2_x(self):
        js = self._read_vendor('datatables.js')
        m = re.search(r'DataTables\s+(\d+\.\d+\.\d+)', js)
        self.assertIsNotNone(m, 'не найден бейдж версии DataTables в datatables.js')
        self.assertEqual(m.group(1).split('.')[0], '1',
                         f'ожидали DataTables 1.x, нашли {m.group(1)} (2.x падает при scrollX)')

    def test_colreorder_version_kept(self):
        js = self._read_vendor('dataTables.colReorder.js')
        m = re.search(r'ColReorder\s+v?(1\.\d+\.\d+)', js)
        self.assertIsNotNone(m, 'не найден бейдж ColReorder')
        self.assertEqual(m.group(1).split('.')[0], '1')

    def test_no_leftover_2_x_bundle_served(self):
        """Класс-маркер из 2.x не должен попадать в основной скрипт."""
        js = self._read_vendor('datatables.js')
        self.assertNotIn('DT-RowGroup', js)
