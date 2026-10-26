"""Бэкфилл позиций сметы из ДДС (здания, разделы, акты) + ДС13 из docx.

Использование:
    python manage.py import_dds --file "ДДС 2026.09.16.xlsx" --dry-run
    python manage.py import_dds --file "ДДС 2026.09.16.xlsx" --apply

Логика:
- строка ДДС (Договор=ДС№N) -> Contract по number;
- позиция ищется среди EstimateConcept этого договора: совпадение
  нормализованного name + amount (с допуском на точку в конце);
- building_number / design_chapter / act заполняются, только если пустые;
  конфликты (уже заполнено другим) — в отчёт, без перезаписи;
- недостающие BuildingType/BuildingNumber/DesignChapter/Act создаются
  (в --apply), всё созданное — в итоговом отчёте на проверку;
- мульти-здания («Коровник № 1,2,3»): FK = первое здание, полный текст
  остаётся в наименовании;
- ДС13 (нет в xlsx): 5 строк из ДС13_Смета_Приложение1.docx зашиты явно.
"""
import re
from datetime import date, datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ProjectContract.models import Act, Contract, EstimateConcept
from ProjectContract.services import log_change
from StaticData.models import BuildingNumber, BuildingType, DesignChapter

DDS_SHEET = 'Родин'

# ДС13 из ДС13_Смета_Приложение1.docx: (здание, раздел, наименование, сумма)
DS13_ROWS = [
    ('Галерея №10', 'Электроснабжение',
     'Заменить наименование, количество, расположение светильников согласно КП.',
     '19000'),
    ('Ангар для спецтехники', 'Электроснабжение',
     'Заменить наименование, количество, расположение светильников согласно КП.',
     '33250'),
    ('Внешние сети ЭОМ', 'Генеральный план',
     'На сводный план сетей нанести фактическое положение сетей ЭОМ в соответствии с исполнительной документацией.',
     '66500'),
    ('Внешние сети НВК', 'Генеральный план',
     'На сводный план сетей нанести фактическое положение сетей НВК в соответствии с исполнительной документацией.',
     '80750'),
    ('Комплекс М1', 'ПОС',
     'В соответствии с замечаниями ИГАСН внести корректировки в раздел ПОС (дороги, забор, пункт мойки колес, временные проезды).',
     '38000'),
]
DS13_CONTRACT_NAME_HINT = 'ДС№13'


def _norm(s):
    return ' '.join(str(s or '').split()).strip()


def _norm_low(s):
    return _norm(s).lower().replace('ё', 'е')


def _parse_building(raw):
    """'Коровник № 1,2' -> ('Коровник', '1'); 'МДМБ' -> ('МДМБ', '-').

    Номер в скобках ('Площадка для телят (1.21 по ГП)') -> ('Площадка для
    телят', '1.21'): иначе каждый прогон предлагает создать дубль здания.
    """
    primary = _norm(raw).split(',')[0].strip()
    m = re.match(r'^(.+?)\s*№\s*(.+)$', primary)
    if m:
        return m.group(1).strip(), m.group(2).strip() or '-'
    m = re.match(r'^(.+?)\s+(\d[\d./]*)$', primary)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r'^(.+?)\s*\(([^)]*)\)\s*$', primary)
    if m:
        num_m = re.search(r'\d[\d./]*', m.group(2))
        if num_m:
            return m.group(1).strip(), num_m.group(0)
    return primary, '-'


def _bkey(tname, num):
    n = (num or '').strip()
    if n == '-':
        n = ''
    return (_norm_low(tname), n)


def _parse_chapter(raw):
    """'КМ и КЖ' -> 'КМ' (первый); '... раздел АР' -> 'АР'."""
    s = _norm(raw)
    m = re.search(r'раздел\s+(.+)$', s, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    parts = re.split(r'\s+и\s+', s, maxsplit=1)
    return parts[0].strip()


#: DDS-название раздела (lower) -> каноничное имя в БД (lower-форма не важна,
#: сопоставление всегда идёт через _norm_low)
CHAPTER_ALIASES = {
    'генплан': 'генеральный план',
    'водоснабжение и канализация': 'внутренние системы водоснабжения и канализации',
    'автоматическая пожарная сигнализаци': 'автоматическая пожарная сигнализация',
}


def chapter_candidates(raw):
    """Кандидаты (ключ_поиска, имя_для_создания, шифр_для_создания) по приоритету.

    1. полное название (с учётом алиасов);
    2. код после «раздел» («... раздел АР» -> «АР», создавать как код);
    3. первая часть «КМ и КЖ» -> «КМ» (создавать с полным текстом).
    """
    full = _norm(raw)
    cands = [(_norm_low(CHAPTER_ALIASES.get(_norm_low(full), full)), full, full)]
    m = re.search(r'раздел\s+(.+)$', full, re.IGNORECASE)
    if m:
        code = m.group(1).strip()
        if _norm_low(code) != _norm_low(full):
            cands.append((_norm_low(code), code, code))
    parts = re.split(r'\s+и\s+', full, maxsplit=1)
    first = parts[0].strip()
    if len(parts) > 1 and _norm_low(first) != _norm_low(full):
        cands.append((_norm_low(first), full, full))
    return cands


def _parse_act_cell(raw):
    """(номер акта | None, дата акта | None).

    В колонке Закрытие иногда лежит дата или текст без номера
    («не закроем») — тогда номер None.
    """
    if raw is None or raw == '':
        return None, None
    if isinstance(raw, datetime):
        return None, raw.date()
    if isinstance(raw, date):
        return None, raw
    s = _norm(raw)
    if re.match(r'^\d{4}-\d{2}-\d{2}', s) or re.match(r'^\d{2}\.\d{2}\.\d{4}', s):
        return None, _parse_date_cell(s)
    s = re.sub(r'(?i)^акт\s*', '', s).strip()
    s = re.sub(r'^[№Nn]+\s*', '', s).strip()
    if not s or not re.search(r'\d', s):
        return None, None
    return s, None


def _parse_date_cell(val):
    if val is None or val == '':
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = _norm(val)
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(val):
    try:
        s = str(val).strip().replace(' ', '').replace(',', '.')
        # Кириллическая 'о' вместо нуля ('15ооо' в ДДС, строка 41).
        s = s.replace('о', '0').replace('О', '0').replace('O', '0')
        return Decimal(s)
    except Exception:
        return None


class Command(BaseCommand):
    help = 'Бэкфилл позиций сметы из ДДС (здания/разделы/акты), idempotent'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True, help='Путь к ДДС .xlsx')
        parser.add_argument('--apply', action='store_true',
                            help='Записать в БД (без флага — только отчёт)')

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            raise CommandError('openpyxl не установлен')
        apply = options['apply']
        mode = 'APPLY' if apply else 'dry-run'

        wb = openpyxl.load_workbook(options['file'], read_only=True, data_only=True)
        if DDS_SHEET not in wb.sheetnames:
            raise CommandError(f'Нет листа {DDS_SHEET}: {wb.sheetnames}')
        ws = wb[DDS_SHEET]

        stats = dict(rows=0, matched=0, miss=0, ambiguous=0, bld_fill=0, ch_fill=0,
                     act_fill=0, bld_new=0, cht_new=0, act_new=0,
                     btype_new=0, conflict=0, ds13=0)
        log = []
        created = {'btype': set(), 'bld': set(), 'ch': set(), 'act': set()}

        # кэши справочников
        btypes = {t.name.strip().lower(): t for t in BuildingType.objects.all()}
        bnums = {}
        for b in BuildingNumber.objects.select_related('name').all():
            tname = (b.name.name if b.name else '').strip().lower()
            bnums[_bkey(tname, b.building_number)] = b
        chapters = {}
        for d in DesignChapter.objects.all():
            chapters[d.name.strip().lower()] = d
            chapters.setdefault(d.short_name.strip().lower(), d)

        def get_building(raw, ctx, create=True):
            if _norm_low(raw).startswith('стадия п'):
                # 'Стадия П, АР' — стадия документации, а не здание: пропуск
                log.append(f'  [{ctx}] здание пропущено (стадия П, не здание): {raw!r}')
                return None
            tname, num = _parse_building(raw)
            key = _bkey(tname, num)
            hit = bnums.get(key)
            if hit:
                return hit
            if not create:
                # У позиции уже есть здание: новое из ДДС не создаём (иначе
                # каждый прогон плодит дубли), расхождение фиксируем строкой.
                log.append(f'  [{ctx}] здание ДДС {raw!r} не создаю (у позиции уже есть здание)')
                return None
            if not apply:
                created['bld'].add(f'{tname} / {num}')
                if _norm_low(tname) not in btypes:
                    created['btype'].add(tname)
                return None
            tkey = _norm_low(tname)
            btype = btypes.get(tkey)
            if btype is None:
                btype = BuildingType.objects.create(name=tname)
                btypes[tkey] = btype
                stats['btype_new'] += 1
                created['btype'].add(tname)
            b = BuildingNumber.objects.create(name=btype, building_number=num)
            bnums[key] = b
            stats['bld_new'] += 1
            created['bld'].add(f'{tname} / {num}')
            log.append(f'  [{ctx}] создано здание: {tname} / {num} (id={b.pk})')
            return b

        def get_chapter(raw, ctx, create=True):
            cands = chapter_candidates(raw)
            for key, _cn, _cs in cands:
                hit = chapters.get(key)
                if hit:
                    return hit
            _key, cname, cshort = cands[-1]
            if not create:
                log.append(f'  [{ctx}] раздел ДДС {raw!r} не создаю (у позиции уже есть раздел)')
                return None
            if not apply:
                created['ch'].add(cname)
                return None
            d = DesignChapter.objects.create(name=cname, short_name=cshort)
            chapters[_norm_low(cname)] = d
            chapters.setdefault(_norm_low(cshort), d)
            stats['cht_new'] += 1
            created['ch'].add(cname)
            log.append(f'  [{ctx}] создан раздел: {cname!r} (id={d.pk})')
            return d

        contracts_cache = {}

        def get_contract(dog):
            key = _norm(dog).replace(' ', '').upper()
            if key in contracts_cache:
                return contracts_cache[key]
            c = Contract.objects.filter(number__isnull=False)
            hit = None
            for cand in c.only('id', 'number', 'name'):
                if (cand.number or '').replace(' ', '').upper() == key:
                    hit = cand
                    break
            contracts_cache[key] = hit
            return hit

        def match_concept(contract, name, amount):
            cands = EstimateConcept.objects.filter(
                estimate__contract=contract).only(
                'id', 'name', 'amount', 'building_number_id',
                'design_chapter_id', 'act_id', 'estimate_id')
            nm = _norm(name)
            try:
                amt = float(amount or 0)
            except (TypeError, ValueError):
                amt = 0

            def amount_ok(c):
                try:
                    return abs(float(c.amount or 0) - amt) <= 0.005
                except (TypeError, ValueError):
                    return False

            # уровень 1: точное совпадение имени
            hits = [c for c in cands
                    if (_norm(c.name) == nm
                        or _norm(c.name).rstrip('.!?…') == nm.rstrip('.!?…'))
                    and amount_ok(c)]
            if hits:
                return hits, 'exact'
            # уровень 2: имя ДДС — суффикс после '|' («Здание | Раздел | Имя»)
            hits = [c for c in cands
                    if _norm(c.name).split('|')[-1].strip() == nm
                    and amount_ok(c)]
            if hits:
                return hits, 'suffix'
            # уровень 3: имя ДДС — подстрока имени позиции
            hits = [c for c in cands if nm and nm in _norm(c.name) and amount_ok(c)]
            if hits:
                return hits, 'substr'
            # уровень 4: уникальная сумма в договоре (для ДС13)
            by_amt = [c for c in cands if amount_ok(c)]
            if len(by_amt) == 1:
                return by_amt, 'amount-only'
            return [], 'none'

        def get_act(contract, act_no, act_date, ctx):
            if not act_no:
                return None
            try:
                act = Act.objects.get(contract=contract, number=act_no)
                if act_date and not act.act_date:
                    if apply:
                        act.act_date = act_date
                        act.save(update_fields=['act_date', 'update_stamp'] if hasattr(act, 'update_stamp') else ['act_date'])
                    log.append(f'  [{ctx}] акту №{act_no}: проставлена дата {act_date}')
                elif act_date and act.act_date and act.act_date != act_date:
                    log.append(f'  [{ctx}] КОНФЛИКТ дат акта №{act_no}: в БД {act.act_date}, в ДДС {act_date} — не трогаю')
                    stats['conflict'] += 1
                return act
            except Act.DoesNotExist:
                if not apply:
                    created['act'].add(f'{contract} / №{act_no} / {act_date}')
                    return None
                act = Act.objects.create(contract=contract, number=act_no, act_date=act_date)
                stats['act_new'] += 1
                created['act'].add(f'{contract} / №{act_no} / {act_date}')
                log.append(f'  [{ctx}] создан акт №{act_no} от {act_date} (id={act.pk})')
                return act

        def bld_key(b):
            if b is None:
                return None
            t = (b.name.name if b and b.name else '') or ''
            return _bkey(t, b.building_number)

        def lookup_chapter_pk(raw):
            for key, _cn, _cs in chapter_candidates(raw):
                hit = chapters.get(key)
                if hit is not None:
                    return hit.pk
            return None

        def disambiguate(hits, bld_raw, ch_raw):
            """Разрешение неоднозначности без ручной работы.

            а) единственное точное совпадение здания ДДС;
            б) единственное совпадение раздела ДДС;
            в) ровно один кандидат с пустым зданием, а остальные противоречат
               зданию ДДС (пары-дубли: 'Коровник №3/№4', 'КПП/Убойная').
            Возвращает (концепт, подуровень) или (None, None).
            """
            bld_key_want = None
            if bld_raw and not _norm_low(bld_raw).startswith('стадия п'):
                tname, num = _parse_building(bld_raw)
                bld_key_want = _bkey(tname, num)
            if bld_key_want is not None:
                exact = [h for h in hits
                         if h.building_number_id is not None
                         and bld_key(h.building_number) == bld_key_want]
                if len(exact) == 1:
                    return exact[0], 'building'
            if ch_raw:
                ch_pk = lookup_chapter_pk(ch_raw)
                if ch_pk is not None:
                    by_ch = [h for h in hits if h.design_chapter_id == ch_pk]
                    if len(by_ch) == 1:
                        return by_ch[0], 'chapter'
            if bld_key_want is not None:
                empty = [h for h in hits if h.building_number_id is None]
                if len(empty) == 1 and all(
                        bld_key(h.building_number) != bld_key_want
                        for h in hits if h.building_number_id is not None):
                    return empty[0], 'building-empty'
            return None, None

        def fill_concept(c, bld, ch, act, ctx):
            upd = []
            if bld is not None:
                if c.building_number_id is None:
                    if apply:
                        c.building_number_id = bld.pk
                        upd.append('building_number')
                    stats['bld_fill'] += 1
                elif bld_key(c.building_number) != bld_key(bld):
                    # дубль-строки зданий (один тип+номер) конфликтом не считаем
                    existing = c.building_number
                    log.append(f'  [{ctx}] КОНФЛИКТ здания поз.{c.pk}: в БД {existing} (id={c.building_number_id}), ДДС {bld} (id={bld.pk}) — не трогаю')
                    stats['conflict'] += 1
            if ch is not None:
                if c.design_chapter_id is None:
                    if apply:
                        c.design_chapter_id = ch.pk
                        upd.append('design_chapter')
                    stats['ch_fill'] += 1
                elif c.design_chapter_id != ch.pk:
                    log.append(f'  [{ctx}] КОНФЛИКТ раздела поз.{c.pk}: в БД {c.design_chapter_id}, ДДС {ch.pk} — не трогаю')
                    stats['conflict'] += 1
            if act is not None:
                if c.act_id is None:
                    if apply:
                        c.act_id = act.pk
                        upd.append('act')
                    stats['act_fill'] += 1
                elif c.act_id != act.pk:
                    log.append(f'  [{ctx}] КОНФЛИКТ акта поз.{c.pk}: в БД {c.act_id}, ДДС {act.pk} — не трогаю')
                    stats['conflict'] += 1
            if upd and apply:
                c.save(update_fields=upd)

        with transaction.atomic():
            for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                if idx == 1 or not row or not row[2]:
                    continue
                bld_raw, ch_raw, name = row[0], row[1], row[2]
                amount = _parse_decimal(row[3])
                stats['rows'] += 1
                # В клетке может быть несколько договоров ('ДС№4,7'): ищем
                # по каждому; целый текст отдельно не требуем.
                contract_keys = [k.strip() for k in str(row[13] or '').split(',') if k.strip()]
                hits, level, used_contract = [], 'none', None
                for ckey in contract_keys:
                    alt = get_contract(ckey)
                    if alt is None:
                        continue
                    hits, level = match_concept(alt, name, amount)
                    if hits:
                        used_contract = alt
                        break
                if not hits and not contract_keys:
                    # Пустая клетка договора (строка 166): уникальное точное
                    # совпадение имени+суммы по всем договорам.
                    nm = _norm(name)
                    try:
                        amt = float(amount or 0)
                    except (TypeError, ValueError):
                        amt = 0

                    def _amount_ok(c):
                        try:
                            return abs(float(c.amount or 0) - amt) <= 0.005
                        except (TypeError, ValueError):
                            return False

                    cands = [c for c in EstimateConcept.objects.only(
                        'id', 'name', 'amount', 'estimate_id').all()
                        if _norm(c.name) == nm and _amount_ok(c)]
                    if len(cands) == 1:
                        hits, level = cands, 'no-contract-exact'
                        used_contract = cands[0].estimate.contract
                if not hits:
                    stats['miss'] += 1
                    if contract_keys and not any(get_contract(k) is not None for k in contract_keys):
                        log.append(f'  Строка {idx}: договор не найден ({row[13]!r}) — пропуск')
                    else:
                        shown = used_contract if used_contract is not None else (row[13] or 'без договора')
                        log.append(f'  Строка {idx}: позиция не найдена ({shown}, {str(name)[:60]!r}, {amount})')
                    continue
                if len(hits) > 1:
                    pick, dlevel = disambiguate(hits, bld_raw, ch_raw)
                    if pick is None:
                        stats['ambiguous'] += 1
                        log.append(f'  Строка {idx}: неоднозначно ({len(hits)} поз. {[h.pk for h in hits]}), пропуск — разобрать вручную: {used_contract}')
                        continue
                    c, level = pick, f'{level}+{dlevel}'
                    log.append(f'  Строка {idx}: неоднозначность снята ({level}): поз.{c.pk}')
                else:
                    c = hits[0]
                if level != 'exact':
                    log.append(f'  Строка {idx}: нечёткое сопоставление ({level}): {used_contract}')
                stats['matched'] += 1
                ctx = f'стр.{idx}/поз.{c.pk}'
                bld = get_building(bld_raw, ctx, create=c.building_number_id is None) if bld_raw else None
                ch = get_chapter(ch_raw, ctx, create=c.design_chapter_id is None) if ch_raw else None
                act_no, act_date_extra = _parse_act_cell(row[14])
                act_date = _parse_date_cell(row[15]) or act_date_extra
                act = get_act(used_contract, act_no, act_date, ctx)
                fill_concept(c, bld, ch, act, ctx)

            # ДС13 (docx, нет в xlsx)
            ds13 = Contract.objects.filter(name__icontains='ДС№13').first() or \
                Contract.objects.filter(number__icontains='13', contractor__name__icontains='Родин').first()
            if ds13 is None and DS13_CONTRACT_NAME_HINT:
                log.append('  ДС13: договор не найден — пропуск блока ДС13')
            if ds13 is not None:
                for bld_raw, ch_raw, name, amount in DS13_ROWS:
                    hits, level = match_concept(ds13, name, Decimal(amount))
                    if not hits:
                        stats['miss'] += 1
                        log.append(f'  ДС13: позиция не найдена ({str(name)[:60]!r}, {amount})')
                        continue
                    if len(hits) > 1:
                        stats['ambiguous'] += 1
                        log.append(f'  ДС13: неоднозначно ({len(hits)} поз.), пропуск: {str(name)[:60]!r}')
                        continue
                    c = hits[0]
                    stats['ds13'] += 1
                    bld = get_building(bld_raw, f'ДС13/поз.{c.pk}', create=c.building_number_id is None)
                    ch = get_chapter(ch_raw, f'ДС13/поз.{c.pk}', create=c.design_chapter_id is None)
                    fill_concept(c, bld, ch, None, f'ДС13/поз.{c.pk}')

            if not apply:
                transaction.set_rollback(True)

        wb.close()
        self.stdout.write(f'[{mode}] строк ДДС: {stats["rows"]}, сопоставлено: {stats["matched"]}, '
                          f'не найдено: {stats["miss"]}, неоднозначных: {stats["ambiguous"]}, ДС13: {stats["ds13"]}')
        stats['act_new'] = len(created['act'])
        stats['bld_new'] = len(created['bld'])
        stats['cht_new'] = len(created['ch'])
        stats['btype_new'] = len(created['btype'])
        self.stdout.write(f'[{mode}] заполнить: зданий={stats["bld_fill"]}, разделов={stats["ch_fill"]}, '
                          f'актов={stats["act_fill"]}; создать: типы зданий={stats["btype_new"]}, '
                          f'здания={stats["bld_new"]}, разделы={stats["cht_new"]}, акты={stats["act_new"]}; '
                          f'конфликтов: {stats["conflict"]}')
        for line in log[:120]:
            self.stdout.write(line)
        if len(log) > 120:
            self.stdout.write(f'  ... ещё {len(log) - 120} строк')
        if created['bld'] or created['ch'] or created['act'] or created['btype']:
            self.stdout.write('Создать предстоит:')
            for k in ('btype', 'bld', 'ch', 'act'):
                for v in sorted(created[k])[:60]:
                    self.stdout.write(f'  {k}: {v}')
        if not apply:
            self.stdout.write(self.style.WARNING('dry-run: БД не менялась. Для записи добавьте --apply'))
        else:
            log_change(action='api:import', details=f'import_dds: fill b{stats["bld_fill"]}/c{stats["ch_fill"]}/a{stats["act_fill"]}')
            self.stdout.write(self.style.SUCCESS('Записано в БД'))
