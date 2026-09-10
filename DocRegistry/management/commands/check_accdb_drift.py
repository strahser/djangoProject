"""Ночной сверщик: живой М1.accdb vs SQL-реестр (канон §4 п.3, DOC-5).

Ручные правки accdb после переключения — отчёт об отличиях, не молчаливое затирание.
Exit 1 при любом расхождении (cron-friendly), иначе OK.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from DocRegistry import accdb as live
from DocRegistry.models import DocRegisterEntry
from DocRegistry.services import compare_registry


class Command(BaseCommand):
    help = 'Сверить живой М1.accdb с DocRegisterEntry (drift-контроль)'

    def handle(self, *args, **options):
        try:
            rows = live.read_registry_rows()
        except Exception as e:
            raise CommandError(f'Не читается accdb: {type(e).__name__}: {e}')
        stored = dict(DocRegisterEntry.objects.values_list('code', 'accdb_row_hash'))
        rep = compare_registry(rows, stored)
        self.stdout.write(
            f'live={len(rows)} sql={len(stored)} '
            f'new={rep["new"]} missing={rep["missing"]} changed={rep["changed"]}')
        if not rep['ok']:
            raise CommandError('DRIFT: реестр SQL разошёлся с живым accdb (см. выше)')
        self.stdout.write(self.style.SUCCESS('drift OK: расхождений нет'))
