"""Сервисы реестра РД: хеш строки accdb, следующий код (канон §3–§4)."""
from __future__ import annotations

import hashlib

from .models import DocRegisterEntry

#: Порядок полей для accdb_row_hash — обязан совпадать с import_accdb_registry.
HASH_FIELDS = (
    'code', 'section', 'building_no', 'cipher', 'file_name',
    'approval_status', 'approval_date', 'submitted_flag', 'change_descr',
    'building_name', 'submit_date', 'acts', 'contractor_new',
)


def accdb_row_hash(values: dict) -> str:
    """sha1 конкатенации полей строки — детектор ручных правок accdb (DOC-5 drift)."""
    joined = '|'.join(str(values.get(f, '') or '') for f in HASH_FIELDS)
    return hashlib.sha1(joined.encode('utf-8')).hexdigest()


def next_code() -> int:
    """Следующий код реестра (max+1); пустой реестр → 1."""
    last = DocRegisterEntry.objects.order_by('-code').values_list('code', flat=True).first()
    return (last or 0) + 1


def compare_registry(live_rows: list[dict], stored: dict[int, str]) -> dict:
    """Сверка живого accdb с SQL: новые/удалённые/изменённые коды (DOC-5 drift).

    live_rows — [{'code': int, 'accdb_row_hash': str, ...}], stored — {code: hash из БД}.
    Чистая функция — тестируется без accdb и БД.
    """
    live = {r['code']: r.get('accdb_row_hash', '') for r in live_rows}
    live_codes, stored_codes = set(live), set(stored)
    changed = sorted(c for c in live_codes & stored_codes if live[c] != stored.get(c))
    new = sorted(live_codes - stored_codes)
    missing = sorted(stored_codes - live_codes)
    return {'new': new, 'missing': missing, 'changed': changed,
            'ok': not (new or missing or changed)}
