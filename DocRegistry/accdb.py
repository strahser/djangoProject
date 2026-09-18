"""Живое чтение М1.accdb (read-only) — общее для импорта и drift-контроля (M1 DOC-1/DOC-5)."""
from __future__ import annotations

import datetime

import pyodbc

ACCDB_PATHS = {
    # Путь К1.accdb пока неизвестен - передавать --accdb явно.
    'M1': r"E:\Проекты Симрус\M1\00 Организация\УтвПРРАБ\М1.accdb",
}
DRIVER = "{Microsoft Access Driver (*.mdb, *.accdb)}"

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

DATE_FIELDS = ('approval_date', 'submit_date')


def _clean(v):
    if v is None:
        return ''
    if isinstance(v, datetime.datetime):
        return v.date().isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    return str(v)


def resolve_path(project, explicit=None):
    if explicit:
        return explicit
    try:
        return ACCDB_PATHS[project]
    except KeyError:
        raise ValueError('Нет пути accdb объекта %r - укажите --accdb' % project)


def connect(path=None, project='M1'):
    return pyodbc.connect(f'DRIVER={DRIVER};DBQ={path or resolve_path(project)};ReadOnly=True')


def table_count(cur, table: str) -> int:
    return cur.execute(f'SELECT COUNT(*) FROM [{table}]').fetchval()


def read_registry_rows(path=None, project='M1') -> list[dict]:
    """Все строки [01 Реестр] как dict полетов Entry (даты '' → None для save)."""
    from .services import accdb_row_hash

    conn = connect(path, project)
    try:
        cur = conn.cursor()
        cols = [c.column_name for c in cur.columns('01 Реестр')]
        out = []
        for row in cur.execute('SELECT * FROM [01 Реестр]').fetchall():
            raw = {c: _clean(v) for c, v in zip(cols, row)}
            values = {COLUMN_MAP[k]: v for k, v in raw.items() if k in COLUMN_MAP}
            values['code'] = int(str(values.get('code', '')).strip())
            for d in DATE_FIELDS:
                values[d] = values.get(d) or None
            values['accdb_row_hash'] = accdb_row_hash(values)
            out.append(values)
        return out
    finally:
        conn.close()


def read_tasks() -> list[dict]:
    """Все строки [02 Задачи] как dict (для маппинга на TaskNode, DOC-5)."""
    conn = connect()
    try:
        cur = conn.cursor()
        cols = [c.column_name for c in cur.columns('02 Задачи')]
        return [{c: _clean(v) for c, v in zip(cols, row)}
                for row in cur.execute('SELECT * FROM [02 Задачи]').fetchall()]
    finally:
        conn.close()
