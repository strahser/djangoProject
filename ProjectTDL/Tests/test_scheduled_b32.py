"""Блок 32: гарды бэкапа БД (ProjectTDL/scheduled)."""
import os
import sqlite3
import tempfile
import time
from unittest.mock import patch

from django.test import TestCase

from ProjectTDL import scheduled


class SqliteBackupTest(TestCase):
    def test_backup_copies_consistently(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'src.sqlite3')
            con = sqlite3.connect(src)
            con.execute('CREATE TABLE t (a INTEGER)')
            con.execute('INSERT INTO t VALUES (42)')
            con.commit()
            con.close()
            dest = os.path.join(tmp, 'dest.sqlite3')
            scheduled._sqlite_backup(src, dest)
            check = sqlite3.connect(dest)
            try:
                self.assertEqual(
                    check.execute('SELECT a FROM t').fetchone()[0], 42)
            finally:
                check.close()

    def test_make_backup_skips_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                scheduled, 'BACKUP_TARGETS',
                [(os.path.join(tmp, 'nope.sqlite3'), '{ts}_db_backup.sqlite3')],
            ), patch.object(scheduled, 'BACKUP_PATH', tmp):
                scheduled.make_db_backup()
            self.assertEqual(os.listdir(tmp), [])

    def test_cleanup_keeps_two_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(scheduled, 'BACKUP_PATH', tmp):
                names = []
                for i in range(4):
                    name = f'2026_01_0{i}_db_backup.sqlite3'
                    path = os.path.join(tmp, name)
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write('x')
                    # старые первее по mtime
                    ts = time.time() - (4 - i) * 100
                    os.utime(path, (ts, ts))
                    names.append(name)
                scheduled._cleanup_old_backups(keep=2)
                left = sorted(os.listdir(tmp))
                self.assertEqual(left, sorted(names[2:]))

    def test_cleanup_ignores_personal_suffix(self):
        # '_personal_db_backup.sqlite3' оканчивается на '_db_backup.sqlite3',
        # но ротируется отдельно (не съедается лимитом рабочей БД).
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(scheduled, 'BACKUP_PATH', tmp):
                for i in range(3):
                    with open(
                        os.path.join(
                            tmp, f'2026_02_0{i}_personal_db_backup.sqlite3'),
                        'w', encoding='utf-8',
                    ) as f:
                        f.write('x')
                with open(os.path.join(tmp, '2026_02_09_db_backup.sqlite3'),
                          'w', encoding='utf-8') as f:
                    f.write('x')
                scheduled._cleanup_old_backups(keep=2)
                left = sorted(os.listdir(tmp))
                self.assertEqual(len([n for n in left if 'personal' in n]), 2)
                self.assertEqual(len(left), 3)
