"""Перестроить материализованные строки ДДС (Ф2).

Использование:
    python manage.py rebuild_cashflow            # все договоры
    python manage.py rebuild_cashflow --contract 6
"""
from django.core.management.base import BaseCommand

from ProjectContract.models import Contract
from ProjectContract.services import rebuild_cashflow


class Command(BaseCommand):
    help = 'Перестроить материализованные строки ДДС'

    def add_arguments(self, parser):
        parser.add_argument('--contract', type=int, default=None,
                            help='ID договора (по умолчанию — все)')

    def handle(self, *args, **options):
        qs = Contract.objects.all().order_by('id')
        if options['contract']:
            qs = qs.filter(pk=options['contract'])
        total = 0
        for contract in qs.iterator():
            n = rebuild_cashflow(contract)
            total += n
            self.stdout.write(f'{contract.pk} {contract.name}: {n} строк')
        self.stdout.write(self.style.SUCCESS(f'Готово: {total} строк ДДС'))
