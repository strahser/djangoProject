"""Сервисы реестра РД: хеш строки accdb, следующий код, типы зданий (канон §3–§4)."""
from __future__ import annotations

import hashlib
import re

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


def next_code(EntryModel) -> int:
    """Следующий код реестра в таблице объекта (max+1); пустая таблица → 1.

    EntryModel — M1Entry/K1Entry: нумерация у каждого объекта своя, таблицы разные.
    """
    last = (EntryModel.objects.order_by('-code').values_list('code', flat=True).first())
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


def signers_for():
    """Подписанты листа согласования — единый общий список по order.

    Фамилии со временем меняются — в PDF фиксируется снимок текущего списка.
    Возврат: list[DocSigner] по order.
    """
    from .models import DocSigner

    return list(DocSigner.objects.order_by('order'))


def building_type_name(building_name: str) -> str:
    """Тип здания из наименования: часть до «№» («Коровник № 4» → «Коровник»).

    Тип общий для всех объектов; номер здания — свой у каждого проекта.
    Пустое наименование → '' (тип не линкуем).
    """
    name = (building_name or '').strip()
    if not name:
        return ''
    return re.sub(r'\s*№.*$', '', name).strip() or name


def get_building_type(building_name: str):
    """Resolve-or-create типа в общем справочнике StaticData по наименованию; '' → None."""
    from StaticData.models import BuildingType

    tname = building_type_name(building_name)
    if not tname:
        return None
    obj, _ = BuildingType.objects.get_or_create(name=tname)
    return obj
