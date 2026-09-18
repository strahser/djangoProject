"""Идемпотентный импорт платежей из Excel (DMC-7).

Использование:
    python manage.py import_payments_excel --file payments.xlsx
    python manage.py import_payments_excel --file payments.xlsx --dry-run
"""
import io as _io
from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date as _parse_date

from ProjectContract.models import Contract, ContractPayments
from ProjectContract.services import log_change


EXPECTED_HEADERS = [
    'contract_id', 'contract_number', 'name', 'price', 'status',
    'due_date', 'calc_type', 'paid_amount', 'paid_date', 'invoice_number',
    'payment_type', 'description',
]


def _parse_date_cell(val):
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val if isinstance(val, date) else val.date()
    s = str(val).strip()
    d = _parse_date(s)
    return d or None


def _parse_decimal(val):
    if val is None:
        return None
    try:
        from decimal import Decimal, ROUND_HALF_UP
        return Decimal(str(val).strip()).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception:
        return None


class Command(BaseCommand):
    help = 'Импорт платежей из Excel (idempotent, openpyxl)'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True, help='Путь к .xlsx файлу')
        parser.add_argument('--dry-run', action='store_true',
                            help='Только проверка, без записи в БД')

    def handle(self, *args, **options):
        filepath = options['file']
        dry_run = options['dry_run']
        try:
            import openpyxl
        except ImportError:
            self.stderr.write(self.style.ERROR(
                'openpyxl не установлен: pip install openpyxl'))
            return

        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            self.stderr.write(self.style.ERROR('Файл пуст'))
            return
        headers = [str(h).strip().lower() if h else '' for h in rows[0]]
        header_map = {h: i for i, h in enumerate(headers) if h}
        missing = [h for h in ('contract_id', 'contract_number', 'name', 'price') if h not in header_map]
        if missing:
            self.stderr.write(self.style.ERROR(f'Отсутствуют обязательные колонки: {", ".join(missing)}'))
            return

        created, updated, skipped, errors = 0, 0, 0, 0
        for line_idx, row in enumerate(rows[1:], start=2):
            cell = lambda h: row[header_map[h]] if h in header_map and header_map[h] < len(row) else None
            contract_id = cell('contract_id')
            contract_number = str(cell('contract_number') or '').strip()
            name = str(cell('name') or '').strip()
            price = _parse_decimal(cell('price'))

            if not name:
                errors += 1
                self.stderr.write(f'  Строка {line_idx}: пустое имя, пропуск')
                continue

            contract = None
            if contract_id is not None:
                try:
                    contract = Contract.objects.get(pk=int(contract_id))
                except (Contract.DoesNotExist, ValueError, TypeError):
                    pass
            if contract is None and contract_number:
                contract = Contract.objects.filter(number=contract_number).first()
            if contract is None:
                errors += 1
                self.stderr.write(f'  Строка {line_idx}: договор не найден (id={contract_id}, №{contract_number}), пропуск')
                continue

            status_val = str(cell('status') or 'planned').strip()
            valid_statuses = dict(ContractPayments.PAYMENT_STATUS).keys()
            if status_val not in valid_statuses:
                errors += 1
                self.stderr.write(f'  Строка {line_idx}: неизвестный статус «{status_val}», пропуск')
                continue

            due_date = _parse_date_cell(cell('due_date'))
            calc_type = str(cell('calc_type') or 'manual').strip()
            paid_amount = _parse_decimal(cell('paid_amount'))
            paid_date = _parse_date_cell(cell('paid_date'))
            invoice_number = str(cell('invoice_number') or '').strip() or None
            payment_type = str(cell('payment_type') or 'intermediate').strip() or None
            description = str(cell('description') or '').strip() or None

            existing = ContractPayments.objects.filter(
                contract=contract, name=name, due_date=due_date).first()

            data = dict(
                contract=contract, name=name, price=price or 0,
                status=status_val, due_date=due_date, calc_type=calc_type,
                paid_amount=paid_amount, paid_date=paid_date,
                invoice_number=invoice_number, payment_type=payment_type,
                payment_description=description,
                made_payment=(status_val == 'paid'),
            )

            if dry_run:
                action_label = 'обновит' if existing else 'создаст'
                self.stdout.write(f'  [dry-run] Строка {line_idx}: {action_label} «{name}» ({price}₽)')
                continue

            if existing:
                for k, v in data.items():
                    setattr(existing, k, v)
                existing.save()
                updated += 1
            else:
                ContractPayments.objects.create(**data)
                created += 1

        summary = f'Создано: {created}, обновлено: {updated}, пропущено: {skipped}, ошибки: {errors}'
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'[dry-run] {summary}'))
        else:
            if created or updated:
                log_change(action='api:import', details=f'imported {created + updated} rows ({summary})')
            self.stdout.write(self.style.SUCCESS(summary))
        wb.close()
        if errors:
            raise CommandError(f'Импорт завершён с ошибками: {errors} строк пропущено')
