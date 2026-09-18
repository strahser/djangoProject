"""Сверка живого accdb объекта с его таблицами (канон §4 п.3, DOC-5).

Таблицы другого объекта не затрагиваются и не влияют на вердикт.
Exit 1 при расхождении (cron-friendly), иначе OK.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from DocRegistry import accdb as live
from DocRegistry.models import PROJECT_CODES, get_registry_or_404
from DocRegistry.services import compare_registry


class Command(BaseCommand):
    help = 'Сверить живой accdb объекта с его таблицами (drift-контроль)'

    def add_arguments(self, parser):
        parser.add_argument('--project', default='M1', choices=list(PROJECT_CODES),
                            help='Объект-реестр (default: M1)')
        parser.add_argument('--accdb', default=None, help='Явный путь к accdb (для К1)')

    def handle(self, *args, **options):
        project = options['project']
        R = get_registry_or_404(project)
        try:
            accdb_path = live.resolve_path(project, options['accdb'])
        except ValueError as e:
            raise CommandError(str(e))
        try:
            rows = live.read_registry_rows(accdb_path)
        except Exception as e:
            raise CommandError(f'Не прочитали accdb: {type(e).__name__}: {e}')
        stored = dict(R['entry'].objects.values_list('code', 'accdb_row_hash'))
        rep = compare_registry(rows, stored)
        self.stdout.write(
            f'[{project}] live={len(rows)} sql={len(stored)} '
            f'new={rep["new"]} missing={rep["missing"]} changed={rep["changed"]}')
        if not rep['ok']:
            raise CommandError('DRIFT: таблицы SQL расходятся с живым accdb (см. выше)')
        self.stdout.write(self.style.SUCCESS('drift OK: расхождений нет'))
