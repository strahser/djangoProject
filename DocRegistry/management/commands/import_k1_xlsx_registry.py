"""Импорт реестра РД К1 из трёх xlsx (МТФ/ФД/КЦ) в таблицы К1.

Источники — копии реестров в DesignBase/data/registry (оригиналы на
Яндекс.Диске не трогаем):
  k1_mtf_2025-10-30.xlsx (лист «реестр», 901 строка) — МТФ, Ефимцево
  k1_fd_2025-10-30.xlsx  (лист «ФД», 135 строк)     — ФД, ферма доращивания
  k1_kc_2025-06-26.xlsx  (лист «КЦ», 87 строк)      — КЦ, кормоцентр

Ключевое отличие К1 от М1: внутри объекта К1 три площадки-проекта
(МТФ / ФД / КЦ). Поэтому:
  * площадки заводятся в общий справочник StaticData.ProjectSite
    (МТФ/ФД/КЦ) — на них ссылаются записи и здания; по ним фильтруют
    и строят отчёт (у М1 площадка одна — «M1»);
  * здание К1 опознаётся по (площадка, № п/гп): «Коровник №1» есть
    и в МТФ, и в ФД, и сливать их нельзя;
  * общий справочник разделов (DocSection) дополняется кодами, которых
    в нём нет (КЖ0/КЖ1/КЖ2/АР1/КМ1/НТК/СОТ/…).

Идемпотентно: update_or_create по кодам. Коды нумеруются по площадкам
с шагом 1000 (МТФ — 1…, ФД — 1001…, КЦ — 2001…), поэтому повторный
импорт обновляет те же записи, а не плодит новые, и по коду видно,
из какого комплекса строка.
"""
from __future__ import annotations

import collections
import datetime
import os
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from DocRegistry.models import DocDeveloper, DocSection, K1Building, K1ChangeLog, K1Entry
from DocRegistry.services import get_building_type

#: Каталог с копиями реестров К1 (DesignBase).
DEFAULT_DIR = Path(r'd:\ПлагиныРевит\DesignBase\data\registry')

#: площадка → (файл, лист реестра, лист зданий, лист разделов, полное имя)
COMPLEXES = (
    ('МТФ', 'k1_mtf_2025-10-30.xlsx', 'реестр', 'Здания МТФ', 'Разделы',
     'Молочная товарная ферма (Ефимцево)'),
    ('ФД', 'k1_fd_2025-10-30.xlsx', 'ФД', 'Здания ФД', 'Разделы',
     'Ферма доращивания'),
    ('КЦ', 'k1_kc_2025-06-26.xlsx', 'КЦ', 'здания', 'Разделы',
     'Кормоцентр'),
)

#: шаг кодов по площадкам (код = offset + позиция внутри площадки)
CODE_OFFSET = {'МТФ': 0, 'ФД': 1000, 'КЦ': 2000}

#: Разработчик по умолчанию для строк без колонки «Разработчик»
#: (реестры К1 ведёт ИСЕТ — см. договор «ДС 5 РД МТФ (ISSET K1)»).
DEFAULT_DEVELOPER = 'ИСЕТ'

#: Колонки листов реестра: ключ → варианты заголовка.
COLS = {
    'row_no': ('№п/п', '№ п/п'),
    'section': ('Раздел',),
    'poz': ('№ п/гп',),
    'building': ('Наименование здания',),
    'volume': ('Наименование тома',),
    'file_name': ('Назв. Эл. файла',),
    'transfer_date': ('дата передачи',),
    'status': ('Статус',),
    'work_status': ('статус передачи в производство работ',
                     'передача в производство работ'),
    'approved_date': ('Дата утверждения в пр-во работ',
                      'дата передачи в пр-во работ'),
    'annulled_date': ('Дата аннулирования',),
    'contractor_date': ('дата передачи подрядчику',),
    'issue_tsg': ('Выдача ТехноСтрой Групп',),
    'contractor': ('Подрядчик',),
    'issue_energo': ('Выдача Энергомонтаж',),
    'act_no': ('Номер акта передачи',),
    'paper_iset': ('кол-во бумж. Экземп от ИСЕТ',),
    'paper_simrus': ('бумажный экземпляр СИМРУС', 'Бумажный экземпляр на объекте'),
    'note': ('примечание',),
    'remarks': ('наличие замечаний',),
    'developer': ('Разработчик',),
}

_REV_SPLIT = re.compile(r'[ _](?:изм|изменение|революц|rev)\b', re.I)
_DATE_SPLIT = re.compile(r'[ _]\d{1,2}[.]\d{1,2}[.]\d{2,4}(?!\d)')
_DATE2_SPLIT = re.compile(r'[ _]\d{1,2}[.]\d{1,2}[.]\d{2}(?!\d)')


def _txt(v) -> str:
    """Значение ячейки → текст; служебный мусор (#N/A, nan) → ''."""
    if v is None:
        return ''
    if isinstance(v, datetime.datetime):
        return v.date().isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else str(v)
    s = str(v).strip()
    return '' if s.lower() in ('nan', 'none', '#n/a', '#n/a!') else s


def _date(v):
    """datetime/date → date; строка-дата (в т.ч. мусорная) → None."""
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    return None


def _norm_section(v: str) -> str:
    return re.sub(r'\s+', ' ', _txt(v).upper().replace('Ё', 'Е')).strip()


def _cipher(file_name: str) -> str:
    """Шифр из имени файла: отрезаем ревизию и дату.

    «308.17.02-1КМ Коровник Изм.1 19.03.2020.pdf» → «308.17.02-1КМ Коровник».
    """
    base = os.path.splitext(_txt(file_name))[0].strip()
    for rx in (_REV_SPLIT, _DATE_SPLIT, _DATE2_SPLIT):
        base = rx.split(base)[0]
    return base.strip(' _-,')[:200]


def _type_key(building_name: str) -> str:
    """Ключ типа здания: до «№» и «(» («Коровник №5 (род.)» → «Коровник»)."""
    return re.split(r'[№(]', _txt(building_name))[0].strip()


def _building_type(building_name: str, section_shorts):
    """Тип здания из наименования; None — если имя не про имя здания.

    В реестрах К1 в колонке «Наименование здания» встречаются и коды
    разделов («ГП», «НВК»), и мусор («2, 4.1-4.4, 6.1, 6.2») — тип здания
    по ним не назначаем, иначе справочник типов засоряется.
    """
    key = _type_key(building_name)
    if not key:
        return None
    if re.fullmatch(r'[\d\s,.\-–—]+', key):
        return None
    if key.upper() in section_shorts:
        return None
    return get_building_type(key)


def _header(rows) -> dict:
    """Карта «заголовок колонки» → индекс (пустые заголовки пропускаем)."""
    hdr = [(str(h).strip() if h not in (None, '') else '') for h in rows[0]]
    return {h: i for i, h in enumerate(hdr) if h}


def _col_index(hdr: dict, key: str):
    for name in COLS[key]:
        if name in hdr:
            return hdr[name]
    return None


class Command(BaseCommand):
    help = ('Импорт реестра РД К1 из трёх xlsx (МТФ/ФД/КЦ): площадки-проекты, '
            'здания, записи реестра, разделы')

    def add_arguments(self, parser):
        parser.add_argument('--dir', default=str(DEFAULT_DIR),
                            help='Каталог с xlsx реестров К1')
        parser.add_argument('--dry-run', action='store_true',
                            help='Только показать, что будет записано')
        parser.add_argument('--report', default=None,
                            help='Файл отчёта импорта (txt)')

    # ------------------------------------------------------------------ чтение
    def _read_sheet(self, wb, sheet):
        if sheet not in wb.sheetnames:
            return None, []
        ws = wb[sheet]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return None, []
        return _header(rows), rows[1:]

    def _load_complex(self, base: Path, site_code, fname, sheet, bld_sheet, sec_sheet):
        """Читает один реестр К1: строки, здания, разделы."""
        import openpyxl

        path = base / fname
        if not path.exists():
            raise CommandError(f'НЕТ ФАЙЛА: {path}')
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        try:
            hdr, rows = self._read_sheet(wb, sheet)
            if hdr is None:
                raise CommandError(f'НЕТ ЛИСТА «{sheet}» в {fname}')
            idx = {k: _col_index(hdr, k) for k in COLS}
            recs = []
            for r in rows:
                if not any(v not in (None, '') for v in r):
                    continue
                rec = {k: (r[i] if i is not None and i < len(r) else None)
                       for k, i in idx.items()}
                recs.append(rec)
            # здания: справочник зданий комплекса
            b_hdr, b_rows = self._read_sheet(wb, bld_sheet)
            buildings = []
            if b_hdr:
                i_poz = b_hdr.get('№ПГП')
                i_name = b_hdr.get('Наименование здания')
                for r in b_rows:
                    poz = _txt(r[i_poz]) if i_poz is not None and i_poz < len(r) else ''
                    name = _txt(r[i_name]) if i_name is not None and i_name < len(r) else ''
                    if not poz and not name:
                        break   # ниже — другая таблица (перечень файлов)
                    if name:
                        buildings.append((poz, name))
            # разделы комплекса
            s_hdr, s_rows = self._read_sheet(wb, sec_sheet)
            sections = []
            if s_hdr:
                i_short = s_hdr.get('Разделы')
                i_name = s_hdr.get('Наименование разделов')
                for r in s_rows:
                    short = (_norm_section(r[i_short])
                             if i_short is not None and i_short < len(r) else '')
                    name = _txt(r[i_name]) if i_name is not None and i_name < len(r) else ''
                    if short:
                        sections.append((short, name))
            return {'site': site_code, 'file': fname, 'sheet': sheet,
                    'rows': recs, 'buildings': buildings, 'sections': sections}
        finally:
            wb.close()

    # ------------------------------------------------------------------ запись
    def handle(self, *args, **options):
        from StaticData.models import ProjectSite

        base = Path(options['dir'])
        dry = options['dry_run']
        report = []

        def say(line=''):
            report.append(line)
            self.stdout.write(line)

        data = []
        for site_code, fname, sheet, bld_sheet, sec_sheet, full in COMPLEXES:
            d = self._load_complex(base, site_code, fname, sheet, bld_sheet, sec_sheet)
            d['full_name'] = full
            data.append(d)
            say(f'{site_code}: {fname} — строк {len(d["rows"])}, '
                f'зданий {len(d["buildings"])}, разделов {len(d["sections"])}')

        # --- площадки-проекты -------------------------------------------
        sites = {}
        for d in data:
            code = d['site']
            obj = ProjectSite.objects.filter(name=code).first()
            created = obj is None
            if created and not dry:
                obj = ProjectSite.objects.create(name=code)
            sites[code] = obj
            say(f'площадка-проект «{code}» ({d["full_name"]}) — '
                f'{"создана" if created else "была"}')

        # --- разделы (общий справочник) ---------------------------------
        existing_sec = {s.short: s for s in DocSection.objects.all()}
        new_sections = {}
        for d in data:
            for short, name in d['sections']:
                if short in existing_sec or short in new_sections:
                    continue
                new_sections[short] = name
        if new_sections and not dry:
            next_code = (DocSection.objects.order_by('-code')
                         .values_list('code', flat=True).first() or 0) + 1
            for short, name in new_sections.items():
                DocSection.objects.create(code=next_code, short=short,
                                          name=name or short)
                next_code += 1
        say(f'разделов добавлено в справочник: {len(new_sections)} '
            f'({", ".join(sorted(new_sections)) or "—"})')

        # --- разработчики ------------------------------------------------
        # «Исет» и «ИСЕТ» — один и тот же разработчик, ключ канонический.
        dev_raw = {DEFAULT_DEVELOPER}
        for d in data:
            for r in d['rows']:
                v = _txt(r.get('developer'))
                if v:
                    dev_raw.add(v)
        dev_names = {}
        for name in sorted(dev_raw):
            dev_names.setdefault(name.strip().upper(), name)
        devs = {}
        for key, name in dev_names.items():
            obj = DocDeveloper.objects.filter(name__iexact=name).first()
            if obj is None and not dry:
                next_code = (DocDeveloper.objects.order_by('-code')
                             .values_list('code', flat=True).first() or 0) + 1
                obj = DocDeveloper.objects.create(code=next_code, name=name)
            devs[key] = obj
        say(f'разработчики: {", ".join(sorted(dev_names.values(), key=str.lower))}')

        # --- здания ------------------------------------------------------
        # ключ: (площадка, поз, наименование) → модель
        bld_keys = []
        seen = set()
        for d in data:
            site = d['site']
            cands = [(poz, name) for poz, name in d['buildings']]
            for r in d['rows']:
                cands.append((_txt(r.get('poz')), _txt(r.get('building'))))
            for poz, name in cands:
                if not name:
                    continue
                key = (site, poz, name)
                if key not in seen:
                    seen.add(key)
                    bld_keys.append(key)
        say(f'зданий К1 (по площадкам): {len(bld_keys)}')

        # --- записи -------------------------------------------------------
        entries = []
        for d in data:
            for r in d['rows']:
                fname = _txt(r.get('file_name'))
                if not fname:
                    continue
                entries.append((d['site'], r, fname))
        say(f'записей реестра К1 (с именем файла): {len(entries)}')

        if dry:
            say('DRY-RUN: запись не выполнялась')
            self._write_report(options.get('report'), report)
            return

        created_e = updated_e = created_b = updated_b = 0
        no_bld = no_sec = 0
        status_count = collections.Counter()
        with transaction.atomic():
            # --- здания: код = offset площадки + позиция ------------------
            blds = {}
            by_name = {}
            bpos = {}
            section_shorts = {s.short.upper() for s in DocSection.objects.all()}
            for site, poz, name in bld_keys:
                bpos[site] = bpos.get(site, 0) + 1
                code = CODE_OFFSET[site] + bpos[site]
                btype = _building_type(name, section_shorts)
                obj, is_new = K1Building.objects.update_or_create(
                    code=code,
                    defaults={'number': poz, 'name': name,
                              'project_site': sites[site], 'building_type': btype})
                if is_new:
                    created_b += 1
                else:
                    updated_b += 1
                blds[(site, poz, name)] = obj
                by_name.setdefault((site, name), obj)
            # --- записи: код = offset площадки + позиция -------------------
            pos_by_site = {}
            for site, r, fname in entries:
                pos_by_site[site] = pos_by_site.get(site, 0) + 1
                poz = _txt(r.get('poz'))
                name = _txt(r.get('building'))
                bld = blds.get((site, poz, name))
                if bld is None and not poz:
                    bld = by_name.get((site, name))
                sec_short = _norm_section(r.get('section'))
                section = (DocSection.objects.filter(short=sec_short).first()
                           if sec_short else None)
                appr = _date(r.get('approved_date')) or _date(r.get('transfer_date'))
                subm = _date(r.get('transfer_date'))
                acts = []
                for key, label in (('act_no', ''), ('issue_tsg', 'ТСГ'),
                                   ('issue_energo', 'Энергомонтаж')):
                    v = _txt(r.get(key))
                    if v:
                        acts.append(f'{label}: {v}' if label else v)
                notes = []
                for key, label in (('note', ''), ('annulled_date', 'аннулировано'),
                                   ('contractor_date', 'передано подрядчику'),
                                   ('remarks', 'замечания'),
                                   ('paper_simrus', 'бумажный экз. СИМРУС'),
                                   ('paper_iset', 'экз. от ИСЕТ')):
                    v = _txt(r.get(key))
                    if v:
                        notes.append(f'{label}: {v}' if label else v)
                dev_name = _txt(r.get('developer')) or DEFAULT_DEVELOPER
                developer = devs.get(dev_name.strip().upper()) or DocDeveloper.objects.filter(
                    name__iexact=dev_name).first()
                code = CODE_OFFSET[site] + pos_by_site[site]
                values = {
                    'project_site': sites[site],
                    'building': bld,
                    'building_no': bld if bld and bld.number == poz else None,
                    'section': section,
                    'volume': _txt(r.get('volume'))[:200],
                    'cipher': _cipher(fname),
                    'file_name': fname[:1000],
                    'approval_status': _txt(r.get('status'))[:50],
                    'approval_date': appr,
                    'submit_date': subm,
                    'submitted_flag': _txt(r.get('work_status'))[:10],
                    'change_descr': '; '.join(notes),
                    'acts': '; '.join(acts)[:500],
                    'developer': developer,
                    'contractor': _txt(r.get('contractor'))[:200],
                }
                _obj, is_new = K1Entry.objects.update_or_create(
                    code=code, defaults=values)
                if is_new:
                    created_e += 1
                else:
                    updated_e += 1
                if bld is None:
                    no_bld += 1
                if section is None:
                    no_sec += 1
                status_count[values['approval_status'] or '—'] += 1
            K1ChangeLog.objects.create(
                field='import', old_value='', source='import',
                new_value=(f'xlsx МТФ/ФД/КЦ: зданий +{created_b}/{updated_b}, '
                           f'записей +{created_e}/{updated_e}'))
        say(f'здания: создано {created_b}, обновлено {updated_b}')
        say(f'записи: создано {created_e}, обновлено {updated_e}')
        say(f'записей без здания: {no_bld}; без раздела: {no_sec}')
        say('статусы: ' + ', '.join(f'{k} — {v}'
                                   for k, v in status_count.most_common()))
        say(f'всего в реестре К1: {K1Entry.objects.count()} записей, '
            f'{K1Building.objects.count()} зданий')
        for site in ('МТФ', 'ФД', 'КЦ'):
            n = K1Entry.objects.filter(project_site__name=site).count()
            nb = K1Building.objects.filter(project_site__name=site).count()
            say(f'  проект {site}: записей {n}, зданий {nb}')
        self._write_report(options.get('report'), report)

    def _write_report(self, path, lines):
        if not path:
            return
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.stdout.write(f'отчёт: {p}')
