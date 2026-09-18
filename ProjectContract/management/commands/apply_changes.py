"""Идемпотентное применение изменений из JSON-файла (EPIC-DJANGOCRM-API).

Формат файла:
{
  "contracts": [ {"id": 1, "name": "...", "price": "100.00", "status": "active", ...} ],
  "payments":  [ {"contract_id": 1, "name": "...", "price": "50.00",
                  "status": "planned", "due_date": "2026-12-01", ...} ]
}

Дедупликация/обновление:
  - contract: по id (или по number если id нет)
  - payment: по (contract, name, due_date)

Использование:
    python manage.py apply_changes --file changes.json
    python manage.py apply_changes --file changes.json --dry-run
"""
import json

from django.core.management.base import BaseCommand, CommandError

from ProjectContract.models import Contract, ContractPayments
from ProjectContract.services import log_change

ALLOWED_CONTRACT_FIELDS = {
    'name', 'number', 'sign_date', 'status', 'stage',
    'next_step', 'next_step_date', 'price',
    'proposal_number', 'proposal_link', 'start_date', 'due_date',
}
ALLOWED_PAYMENT_FIELDS = {
    'name', 'payment_type', 'payment_description', 'price', 'percent',
    'calc_type', 'base_amount', 'status', 'paid_amount', 'paid_date',
    'invoice_number', 'start_date', 'due_date',
}
VALID_STATUSES = set(dict(ContractPayments.PAYMENT_STATUS).keys())


class Command(BaseCommand):
    help = 'Применить изменения из JSON (contracts/payments), idempotent'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True, help='Путь к .json файлу')
        parser.add_argument('--dry-run', action='store_true',
                            help='Только проверка, без записи в БД')

    def handle(self, *args, **options):
        from ProjectContract.models import CONTRACT_STAGES
        valid_stages = set(dict(CONTRACT_STAGES).keys())
        with open(options['file'], encoding='utf-8') as fh:
            data = json.load(fh)
        dry = options['dry_run']
        created = updated = errors = 0

        for item in data.get('contracts', []):
            try:
                self._apply_contract(item, valid_stages, dry=dry)
            except ValueError as e:
                errors += 1
                self.stderr.write(f'  contract skipped: {e}')
            else:
                created += 1

        for item in data.get('payments', []):
            try:
                self._apply_payment(item, dry=dry)
            except ValueError as e:
                errors += 1
                self.stderr.write(f'  payment skipped: {e}')
            else:
                created += 1

        if not dry and created:
            log_change(action='api:apply', details=f'applied {created} records')
        self.stdout.write(
            self.style.SUCCESS(f'Applied: {created}, errors: {errors}'
                               + (' [dry-run]' if dry else '')))
        if errors:
            raise CommandError(f'Применение завершено с ошибками: {errors}')

    def _resolve_contract(self, item):
        cid = item.get('id') or item.get('contract_id')
        if cid is not None:
            c = Contract.objects.filter(pk=cid).first()
            if c:
                return c
        num = item.get('number')
        if num:
            c = Contract.objects.filter(number=num).first()
            if c:
                return c
        raise ValueError(f'договор не найден (id={cid}, №{num})')

    def _apply_contract(self, item, valid_stages, dry):
        c = self._resolve_contract(item)
        new_status = item.get('status')
        if new_status and new_status not in dict(
                Contract.CONTRACT_STATUS).keys():
            raise ValueError(f'неизвестный статус {new_status}')
        new_stage = item.get('stage')
        if new_stage and new_stage not in valid_stages:
            raise ValueError(f'неизвестный этап {new_stage}')
        if dry:
            return
        for k, v in item.items():
            if k in ALLOWED_CONTRACT_FIELDS:
                setattr(c, k, v)
        c.save(update_fields=[k for k in item if k in ALLOWED_CONTRACT_FIELDS])
        log_change(contract=c, action='api:apply',
                   details=f'contract {c.name} updated')

    def _apply_payment(self, item, dry):
        c = self._resolve_contract(item)
        name = item.get('name')
        due_date = item.get('due_date')
        if not name:
            raise ValueError('payment без имени')
        existing = ContractPayments.objects.filter(
            contract=c, name=name, due_date=due_date).first()
        if existing is None:
            raise ValueError(f'платёж «{name}» не найден для обновления '
                             f'(apply_changes не создаёт платежи; '
                             f'используйте import_payments_excel)')
        st = item.get('status')
        if st and st not in VALID_STATUSES:
            raise ValueError(f'неизвестный статус {st}')
        if dry:
            return
        for k, v in item.items():
            if k in ALLOWED_PAYMENT_FIELDS and k in ('name', 'due_date'):
                pass  # ключи идентификации не трогаем
            if k in ALLOWED_PAYMENT_FIELDS and k not in ('name', 'due_date'):
                setattr(existing, k, v)
        existing.save(update_fields=[
            k for k in item if k in ALLOWED_PAYMENT_FIELDS
            and k not in ('name', 'due_date')])
        log_change(contract=c, payment=existing, action='api:apply',
                   details=f'payment {existing.name} updated')