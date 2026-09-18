"""Проверить наступившие напоминания (DMX-2, C9).

Источники (единое правило DMC-5: дата <= сегодня):
  - ручные ContractReminder (не отправлено, не закрыто)
  - просроченные платежи (due_date, статус != paid)
  - просроченные задачи (due_date, статус != «Закрыто»)
  - просроченные «следующие шаги» этапов (ContractStageLog, как check_stage_reminders)

Использование:
    python manage.py check_reminders              # отчёт в stdout
    python manage.py check_reminders --warn       # + loguru-warning каждому
    python manage.py check_reminders --mark-sent  # ручные перевести в is_sent
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from ProjectContract.models import (
    ContractPayments,
    ContractReminder,
    ContractStageLog,
)
from ProjectTDL.models import TaskNode


class Command(BaseCommand):
    help = 'Напоминания: ручные + просрочки платежей/задач/этапов (C9)'

    def add_arguments(self, parser):
        parser.add_argument('--warn', action='store_true',
                            help='Дополнительно писать loguru-warning на каждое')
        parser.add_argument('--mark-sent', action='store_true',
                            help='Ручные наступившие перевести в is_sent')

    def handle(self, *args, **options):
        today = timezone.localdate()
        warn = options['warn']

        manual = (ContractReminder.objects
                  .filter(is_sent=False, is_done=False, due_date__lte=today)
                  .select_related('contract', 'task', 'payment', 'recipient')
                  .order_by('due_date', 'id'))
        payments = (ContractPayments.objects
                    .filter(due_date__lte=today, due_date__isnull=False)
                    .exclude(status='paid')
                    .select_related('contract')
                    .order_by('due_date', 'id'))
        tasks = (TaskNode.objects
                 .filter(due_date__lte=today, due_date__isnull=False)
                 .exclude(status__name='Закрыто')
                 .select_related('project_site', 'status', 'contract')
                 .order_by('due_date', 'id'))
        steps = (ContractStageLog.objects
                 .filter(is_next_step=True, date__lte=today)
                 .select_related('contract', 'user')
                 .order_by('date', 'contract_id'))

        if warn:
            from loguru import logger
            for r in manual:
                target = r.task or r.payment or r.contract
                logger.warning(
                    'Напоминание: {target} — {message} (до {date:%d.%m.%Y})',
                    target=target, message=r.message or 'напомнить',
                    date=r.due_date)
            for p in payments:
                logger.warning(
                    'Просрочен платёж: {contract} — «{name}» '
                    '({date:%d.%m.%Y}, статус {status})',
                    contract=p.contract, name=p.name,
                    date=p.due_date, status=p.get_status_display())
            for t in tasks:
                logger.warning(
                    'Просрочена задача: «{name}» ({date:%d.%m.%Y})',
                    name=t.name, date=t.due_date)
            for s in steps:
                logger.warning(
                    'Просрочен следующий шаг: {contract} — {stage} '
                    '({date:%d.%m.%Y}) {notes}',
                    contract=s.contract, stage=s.get_stage_display(),
                    date=s.date, notes=s.notes)

        for r in manual:
            target = r.task or r.payment or r.contract
            self.stdout.write(f'Напомнить [{r.due_date:%d.%m.%Y}]: {target}'
                              + (f' — {r.message}' if r.message else ''))
        for p in payments:
            self.stdout.write(
                f'Платёж [{p.due_date:%d.%m.%Y}]: {p.contract} — «{p.name}»')
        for t in tasks:
            self.stdout.write(f'Задача [{t.due_date:%d.%m.%Y}]: «{t.name}»')
        for s in steps:
            self.stdout.write(
                f'Шаг [{s.date:%d.%m.%Y}]: {s.contract} — '
                f'{s.get_stage_display()}')

        marked = 0
        n_manual = manual.count()
        n_payments = payments.count()
        n_tasks = tasks.count()
        n_steps = steps.count()
        if options['mark_sent']:
            now = timezone.now()
            marked = manual.update(is_sent=True, sent_at=now)

        total = n_manual + n_payments + n_tasks + n_steps
        self.stdout.write(self.style.SUCCESS(
            f'Напоминаний: {total} '
            f'(ручные: {n_manual}, платежи: {n_payments}, '
            f'задачи: {n_tasks}, шаги: {n_steps}'
            + (f', отмечено отправленными: {marked}' if options['mark_sent'] else '')
            + ')'))
