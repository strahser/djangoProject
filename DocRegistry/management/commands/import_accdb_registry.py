"""Импорт реестра РД из живого М1.accdb в SQL (канон §4, DOC-1).

Источник — read-only, counts обязаны сойтись (368/92/78/41),
иначе STOP без записи. Идемпотентно: update_or_create по code.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from DocRegistry import accdb as live
from DocRegistry.models import DocChangeLog, DocRegisterEntry

EXPECTED_COUNTS = {
    '01 Реестр': 368,
    '02 Задачи': 92,
    'Здания': 78,
    'Разделы': 41,
}


class Command(BaseCommand):
    help = 'Импорт [01 Реестр] из М1.accdb (read-only) в DocRegisterEntry'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Только сверка counts, без записи')

    def handle(self, *args, **options):
        conn = live.connect()
        try:
            cur = conn.cursor()
            for table, expected in EXPECTED_COUNTS.items():
                n = live.table_count(cur, table)
                self.stdout.write(f'{table}: {n} (ожидалось {expected})')
                if n != expected:
                    raise CommandError(
                        f'COUNT MISMATCH [{table}]: {n} != {expected} — STOP без записи')
        finally:
            conn.close()

        rows = live.read_registry_rows()
        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f'dry-run OK: {len(rows)} строк'))
            return

        created, updated = 0, 0
        for values in rows:
            _obj, is_new = DocRegisterEntry.objects.update_or_create(
                code=values['code'], defaults=values)
            if is_new:
                created += 1
            else:
                updated += 1
        DocChangeLog.objects.create(
            field='import', old_value='', new_value=f'{created}+{updated}',
            source='import')
        self.stdout.write(self.style.SUCCESS(
            f'Импорт: создано {created}, обновлено {updated}'))
