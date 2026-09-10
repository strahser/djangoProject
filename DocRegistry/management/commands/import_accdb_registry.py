"""Импорт реестра РД из живого М1.accdb в SQL (канон §4, DOC-1).

Источник — read-only, counts обязаны сойтись (368/92/78/41),
иначе STOP без записи. Идемпотентно: update_or_create по code.
"""
from __future__ import annotations

import datetime

import pyodbc
from django.core.management.base import BaseCommand, CommandError

from DocRegistry.models import DocChangeLog, DocRegisterEntry
from DocRegistry.services import HASH_FIELDS, accdb_row_hash

ACCDB = r"E:\Проекты Симрус\M1\00 Организация\УтвПРРАБ\М1.accdb"
DRIVER = "{Microsoft Access Driver (*.mdb, *.accdb)}"

EXPECTED_COUNTS = {
    '01 Реестр': 368,
    '02 Задачи': 92,
    'Здания': 78,
    'Разделы': 41,
}

#: accdb-колонка → поле DocRegisterEntry
COLUMN_MAP = {
    'код': 'code',
    'раздел': 'section',
    'Номер здания': 'building_no',
    'шифр': 'cipher',
    'Назв Эл файла': 'file_name',
    'согласование': 'approval_status',
    'дата согласования': 'approval_date',
    'подано на согласование': 'submitted_flag',
    'Описание изм': 'change_descr',
    'Наименование здания': 'building_name',
    'Дата подачи на согласование': 'submit_date',
    'Акты': 'acts',
    'разраб_нов': 'contractor_new',
}


def _clean(v):
    if v is None:
        return ''
    if isinstance(v, datetime.datetime):
        return v.date().isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    return str(v)


class Command(BaseCommand):
    help = 'Импорт [01 Реестр] из М1.accdb (read-only) в DocRegisterEntry'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Только сверка counts, без записи')

    def handle(self, *args, **options):
        conn = pyodbc.connect(f'DRIVER={DRIVER};DBQ={ACCDB};ReadOnly=True')
        cur = conn.cursor()
        try:
            for table, expected in EXPECTED_COUNTS.items():
                n = cur.execute(f'SELECT COUNT(*) FROM [{table}]').fetchval()
                self.stdout.write(f'{table}: {n} (ожидалось {expected})')
                if n != expected:
                    raise CommandError(
                        f'COUNT MISMATCH [{table}]: {n} != {expected} — STOP без записи')
        except CommandError:
            raise
        except Exception as e:
            raise CommandError(f'Ошибка чтения accdb: {e}')

        cols = [c.column_name for c in cur.columns('01 Реестр')]
        rows = cur.execute('SELECT * FROM [01 Реестр]').fetchall()
        conn.close()

        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f'dry-run OK: {len(rows)} строк'))
            return

        created, updated = 0, 0
        for row in rows:
            raw = {c: _clean(v) for c, v in zip(cols, row)}
            values = {COLUMN_MAP[k]: v for k, v in raw.items() if k in COLUMN_MAP}
            try:
                values['code'] = int(str(values.get('code', '')).strip())
            except ValueError:
                raise CommandError(f'Некорректный код: {values.get("code")!r}')
            # Пустая строка в DateField падает на save() — только None.
            for d in ('approval_date', 'submit_date'):
                values[d] = values.get(d) or None
            values['accdb_row_hash'] = accdb_row_hash(values)
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
