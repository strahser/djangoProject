"""Проверить просроченные «следующие шаги» этапов (DMC-5).

Использование:
    python manage.py check_stage_reminders                # отчёт в stdout
    python manage.py check_stage_reminders --warn         # + loguru-warning каждому
    python manage.py check_stage_reminders --to-step user # (задел на уведомления)
"""
from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone

from ProjectContract.models import Contract, ContractStageLog
from ProjectContract.services import transition_contract_stage


class Command(BaseCommand):
    help = 'Найти договоры с просроченными «следующими шагами» (этапы, C3/D9)'

    def add_arguments(self, parser):
        parser.add_argument('--warn', action='store_true',
                            help='Дополнительно писать loguru-warning на каждый просроченный шаг')
        parser.add_argument('--to-step', default=None,
                            help='user/email получателя (задел на уведомления)')

    def handle(self, *args, **options):
        today = timezone.localdate() or date.today()
        overdue = (ContractStageLog.objects
                   .filter(is_next_step=True, date__lte=today)
                   .select_related('contract', 'user')
                   .order_by('date', 'contract_id'))
        if options['warn']:
            from loguru import logger
            for step in overdue:
                logger.warning(
                    'Просрочен следующий шаг: {contract} — {stage} ({date:%d.%m.%Y}) {notes}',
                    contract=step.contract.name or step.contract_id,
                    stage=step.get_stage_display(), date=step.date, notes=step.notes)
        targets = {}
        for step in overdue:
            targets.setdefault(step.contract_id, []).append(step)
        count = overdue.count()
        for cid, steps in targets.items():
            names = ', '.join(s.get_stage_display() for s in steps)
            self.stdout.write(f'Договор {cid}: {names}')
        self.stdout.write(self.style.SUCCESS(f'Просроченных шагов: {count}'))