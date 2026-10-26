"""Разбор имён позиций вида «Здание | Раздел | Наименование».

Использование:
    python manage.py split_concept_names
    python manage.py split_concept_names --apply

Здание и раздел разносится по FK (только в пустые; конфликты — в отчёт
без перезаписи), в name остаётся только наименование.
Справочники резолвятся той же логикой, что в import_dds
(недостающие создаются, всё созданное — в отчёт).
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from ProjectContract.models import EstimateConcept
from ProjectContract.services import log_change
from ProjectContract.management.commands.import_dds import (
    _bkey, _norm, _norm_low, _parse_building, chapter_candidates,
)
from StaticData.models import BuildingNumber, BuildingType, DesignChapter


class Command(BaseCommand):
    help = 'Разбор «Здание | Раздел | Имя» в позициях сметы (idempotent)'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Записать в БД (без флага — только отчёт)')

    def handle(self, *args, **options):
        apply = options['apply']
        mode = 'APPLY' if apply else 'dry-run'
        stats = dict(found=0, split=0, miss=0, conflict=0,
                     bld_new=0, cht_new=0, btype_new=0)
        log = []
        created = {'btype': set(), 'bld': set(), 'ch': set()}

        btypes = {t.name.strip().lower(): t for t in BuildingType.objects.all()}
        bnums = {}
        for b in BuildingNumber.objects.select_related('name').all():
            tname = (b.name.name if b.name else '').strip().lower()
            bnums[_bkey(tname, b.building_number)] = b
        chapters = {}
        for d in DesignChapter.objects.all():
            chapters[d.name.strip().lower()] = d
            chapters.setdefault(d.short_name.strip().lower(), d)

        def get_building(raw, ctx):
            if _norm_low(raw).startswith('стадия п'):
                return None
            tname, num = _parse_building(raw)
            key = _bkey(tname, num)
            hit = bnums.get(key)
            if hit:
                return hit
            created['bld'].add(f'{tname} / {num}')
            if not apply:
                return None
            tkey = _norm_low(tname)
            btype = btypes.get(tkey)
            if btype is None:
                btype = BuildingType.objects.create(name=tname)
                btypes[tkey] = btype
                created['btype'].add(tname)
            b = BuildingNumber.objects.create(name=btype, building_number=num)
            bnums[key] = b
            log.append(f'  [{ctx}] создано здание: {tname} / {num} (id={b.pk})')
            return b

        def get_chapter(raw, ctx):
            cands = chapter_candidates(raw)
            for key, _cn, _cs in cands:
                hit = chapters.get(key)
                if hit:
                    return hit
            _key, cname, cshort = cands[-1]
            created['ch'].add(cname)
            if not apply:
                return None
            d = DesignChapter.objects.create(name=cname, short_name=cshort)
            chapters[_norm_low(cname)] = d
            chapters.setdefault(_norm_low(cshort), d)
            log.append(f'  [{ctx}] создан раздел: {cname!r} (id={d.pk})')
            return d

        def same_bld(a, b):
            if a is None or b is None:
                return False
            t1 = (a.name.name if a.name else '') or ''
            t2 = (b.name.name if b.name else '') or ''
            return _bkey(t1, a.building_number) == _bkey(t2, b.building_number)

        with transaction.atomic():
            qs = EstimateConcept.objects.filter(name__contains='|').order_by('id')
            for c in qs:
                stats['found'] += 1
                segs = [_norm(s) for s in (c.name or '').split('|')]
                segs = [s for s in segs if s]
                if len(segs) < 3:
                    stats['miss'] += 1
                    log.append(f'  поз.{c.pk}: частей {len(segs)} (< 3) — пропуск: {(c.name or "")[:80]!r}')
                    continue
                bld_txt, ch_txt = segs[0], segs[1]
                new_name = ' | '.join(segs[2:])
                ctx = f'поз.{c.pk}'
                bld = get_building(bld_txt, ctx)
                ch = get_chapter(ch_txt, ctx)
                problems = []
                if bld is not None and c.building_number_id is not None \
                        and not same_bld(c.building_number, bld):
                    problems.append(
                        f'здание: в БД {c.building_number} (id={c.building_number_id}), '
                        f'в имени {bld} (id={bld.pk})')
                if ch is not None and c.design_chapter_id is not None \
                        and c.design_chapter_id != ch.pk:
                    problems.append(
                        f'раздел: в БД id={c.design_chapter_id}, в имени id={ch.pk}')
                if problems:
                    stats['conflict'] += 1
                    log.append(f'  {ctx}: КОНФЛИКТ ({ "; ".join(problems) }) — не трогаю')
                    continue
                upd = {}
                if bld is not None and c.building_number_id is None:
                    upd['building_number_id'] = bld.pk
                if ch is not None and c.design_chapter_id is None:
                    upd['design_chapter_id'] = ch.pk
                if _norm(c.name) != new_name:
                    upd['name'] = new_name
                if upd:
                    stats['split'] += 1
                    log.append(f'  {ctx}: {list(upd)} <- {(c.name or "")[:70]!r}')
                    if apply:
                        for k, v in upd.items():
                            setattr(c, k, v)
                        c.save(update_fields=list(upd))
            if not apply:
                transaction.set_rollback(True)

        self.stdout.write(
            f'[{mode}] с разделителем: {stats["found"]}, разобрать: {stats["split"]}, '
            f'пропуск: {stats["miss"]}, конфликтов: {stats["conflict"]}')
        self.stdout.write(
            f'[{mode}] создать: типы зданий={len(created["btype"])}, '
            f'здания={len(created["bld"])}, разделы={len(created["ch"])}')
        for line in log[:80]:
            self.stdout.write(line)
        if len(log) > 80:
            self.stdout.write(f'  ... ещё {len(log) - 80} строк')
        for k in ('btype', 'bld', 'ch'):
            for v in sorted(created[k]):
                self.stdout.write(f'  new {k}: {v}')
        if not apply:
            self.stdout.write(self.style.WARNING('dry-run: БД не менялась. Для записи добавьте --apply'))
        else:
            log_change(action='api:import', details=f'split_concept_names: {stats["split"]} позиций')
            self.stdout.write(self.style.SUCCESS('Записано в БД'))
