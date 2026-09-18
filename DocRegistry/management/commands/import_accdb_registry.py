"""Импорт реестра РД из живого accdb объекта в его таблицы (канон §4).

Порядок (как в исходнике): справочники (Здания, Разделы, Разработчик,
Согласование → сид подписантов) → [01 Реестр] (коды FK резолвятся в значения) →
история [Замечания к чертежам] (по Код реестра).

Источник — read-only, counts обязаны сойтись, иначе STOP без записи.
Идемпотентно: update_or_create по кодам accdb.
Каждый объект пишется только в свои таблицы (--project M1|K1).
"""
from __future__ import annotations

import datetime

from django.core.management.base import BaseCommand, CommandError

from DocRegistry import accdb as live
from DocRegistry.models import (
    PROJECT_CODES,
    DocDeveloper,
    DocProject,
    DocSection,
    DocSigner,
    get_registry_or_404,
)
from DocRegistry.services import get_building_type

EXPECTED_COUNTS = {
    'M1': {
        'Здания': 78,
        'Разделы': 41,
        'Разработчик': 14,
        'Согласование': 4,
        '01 Реестр': 368,
        '02 Задачи': 92,
        'Замечания к чертежам': 3,
    },
    'K1': {},
}


def _clean(v):
    if v is None:
        return ''
    if isinstance(v, datetime.datetime):
        return v.date().isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    return str(v)


def _to_int(v):
    try:
        return int(str(v or '').strip())
    except (ValueError, TypeError):
        return None


class Command(BaseCommand):
    help = 'Импорт реестра РД из accdb объекта в его таблицы: справочники → записи → история замечаний'

    def add_arguments(self, parser):
        parser.add_argument('--project', default='M1', choices=list(PROJECT_CODES),
                            help='Объект-реестр (default: M1)')
        parser.add_argument('--accdb', default=None, help='Явный путь к accdb (для К1)')
        parser.add_argument('--dry-run', action='store_true', help='Только сверка counts, без записи')

    def handle(self, *args, **options):
        project = options['project']
        R = get_registry_or_404(project)
        Building, Entry, Remark, ChangeLog = R['building'], R['entry'], R['remark'], R['changelog']
        try:
            accdb_path = live.resolve_path(project, options['accdb'])
        except ValueError as e:
            raise CommandError(str(e))
        conn = live.connect(accdb_path)
        try:
            cur = conn.cursor()
            for table, expected in EXPECTED_COUNTS[project].items():
                n = live.table_count(cur, table)
                self.stdout.write(f'{table}: {n} (ожидалось {expected})')
                if n != expected:
                    raise CommandError(
                        f'COUNT MISMATCH [{table}]: {n} != {expected} — STOP без записи')
            ref = {}
            for table in ('Здания', 'Разделы', 'Разработчик', 'Согласование'):
                cols = [c.column_name for c in cur.columns(table)]
                ref[table] = [{c: _clean(v) for c, v in zip(cols, r)}
                              for r in cur.execute(f'SELECT * FROM [{table}]').fetchall()]
            cols = [c.column_name for c in cur.columns('Замечания к чертежам')]
            remarks = [{c: _clean(v) for c, v in zip(cols, r)}
                       for r in cur.execute('SELECT * FROM [Замечания к чертежам]').fetchall()]
        finally:
            conn.close()

        rows = live.read_registry_rows(accdb_path)
        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f'dry-run OK: {len(rows)} строк'))
            return

        # 1. Справочники. Здания — в таблицу объекта; разделы/разработчики/подписанты — общие.
        proj, _ = DocProject.objects.update_or_create(
            code=project, defaults={'name': {'M1': 'Волоколамск', 'K1': 'Калуга'}[project]})
        if project == 'M1':
            DocProject.objects.update_or_create(
                code='M1',
                defaults={
                    'name': 'Волоколамск',
                    'customer': 'ООО «ТиЭйч-РУС Милк Фуд»',
                    'object_name': '«Комплекс молочного животноводства на 6000 фуражных коров»',
                    'object_address': 'Московская область, Волоколамский район, территория ФГОУ СПО '
                                      'Волоколамский аграрный техникум “Холмогорка”',
                    'designer': 'ИП РОДИН'})
        for r in ref['Здания']:
            code = _to_int(r.get('Код здания'))
            vals = {'number': r.get('№ Здания', ''), 'name': r.get('Наименование здания', '')}
            btype = get_building_type(vals['name'])
            if btype is not None:
                vals['building_type'] = btype
            Building.objects.update_or_create(code=code, defaults=vals)
        for r in ref['Разделы']:
            DocSection.objects.update_or_create(
                code=_to_int(r.get('код раздела')), defaults={
                    'short': r.get('Разделы', ''), 'name': r.get('Наименование разделов', '')})
        for r in ref['Разработчик']:
            DocDeveloper.objects.update_or_create(
                code=_to_int(r.get('Код')), defaults={'name': r.get('Разработчик', '')})
        if DocSigner.objects.count() == 0:
            for r in ref['Согласование']:
                person = r.get('ФИО', '')
                DocSigner.objects.create(
                    order=_to_int(r.get('код согласования')) or 0,
                    position=(r.get('Должность', '') or '').strip(),
                    company=r.get('Компания', ''), person=person,
                    mark=r.get('Отметка о согласовании', ''),
                    # штамп «Согласовано» — менеджер по проектированию (э-подпись с датой)
                    stamp='Страхов' in person)
            self.stdout.write('Подписанты: сид из [Согласование] ({})'.format(len(ref['Согласование'])))

        buildings = {b.code: b for b in Building.objects.all()}
        sections = {s.code: s for s in DocSection.objects.all()}
        developers = {d.code: d for d in DocDeveloper.objects.all()}

        # 2. Записи (FK резолвятся; неизвестный код → None + предупреждение, не STOP)
        warns: set[str] = set()
        created, updated = 0, 0
        for values in rows:
            raw = {k: values.pop(k) for k in ('section', 'building_no', 'building_name', 'contractor_new')}
            sec = sections.get(_to_int(raw['section']))
            bno = buildings.get(_to_int(raw['building_no']))
            bld = buildings.get(_to_int(raw['building_name']))
            dev = developers.get(_to_int(raw['contractor_new']))
            for label, obj, rv in (('раздел', sec, raw['section']),
                                   ('здание(№)', bno, raw['building_no']),
                                   ('здание', bld, raw['building_name']),
                                   ('разработчик', dev, raw['contractor_new'])):
                if obj is None and (rv or '').strip():
                    warns.add(f'{label}={rv}')
            values.update(section=sec, building_no=bno, building=bld, developer=dev)
            _obj, is_new = Entry.objects.update_or_create(
                code=values['code'], defaults=values)
            created, updated = created + (1 if is_new else 0), updated + (0 if is_new else 1)
        if warns:
            self.stdout.write(self.style.WARNING(f'Неизвестные коды справочников → None: {sorted(warns)}'))

        # 3. История замечаний (по Код реестра)
        hist = 0
        for r in remarks:
            code = _to_int(r.get('Код реестра'))
            entry = Entry.objects.filter(code=code).first() if code else None
            if entry is None:
                self.stdout.write(self.style.WARNING(
                    f"Замечание {r.get('Код замечания')}: нет записи {code} — пропущено"))
                continue
            if not entry.history_remarks.filter(text=r.get('Замечание', '')).exists():
                Remark.objects.create(
                    entry=entry, text=r.get('Замечание', ''),
                    remark_date=r.get('Дата замечания') or None)
                hist += 1

        ChangeLog.objects.create(
            field='import', old_value='', new_value=f'{created}+{updated}',
            source='import')
        self.stdout.write(self.style.SUCCESS(
            f'Импорт {project}: создано {created}, обновлено {updated}, история замечаний +{hist}'))
