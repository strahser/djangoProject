"""Блок 32: гарды стабилизации БД (прагмы, индексы, бэкап)."""
from django.db import connection
from django.test import TestCase


class SqlitePragmasTest(TestCase):
    def _pragma(self, name):
        with connection.cursor() as cur:
            cur.execute(f'PRAGMA {name}')
            return cur.fetchone()[0]

    def test_busy_timeout_configured(self):
        from djangoProject.db_config import BUSY_TIMEOUT_MS
        self.assertEqual(self._pragma('busy_timeout'), BUSY_TIMEOUT_MS)

    def test_wal_or_memory_journal(self):
        # Файловая БД -> wal; тестовая in-memory -> memory (пинов нет).
        self.assertIn(self._pragma('journal_mode'), ('wal', 'memory'))


class EmailIndexTest(TestCase):
    def _index_columns(self):
        with connection.cursor() as cur:
            names = connection.introspection.get_constraints(
                cur, 'Emails_email')
        return [tuple(c['columns']) for c in names.values() if c['index']]

    def test_folder_stamp_index(self):
        self.assertIn(('folder', 'email_stamp'), self._index_columns())

    def test_folder_unread_index(self):
        self.assertIn(('folder', 'is_read'), self._index_columns())
