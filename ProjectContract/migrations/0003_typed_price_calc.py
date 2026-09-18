# Generated for Ф0 рефакторинга: типизированные расчёты цены вместо eval-формул.
import re
from decimal import Decimal

from django.db import migrations, models


_SIMPLE_FORMULA = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*\*\s*(\d+(?:\.\d+)?)\s*$')


def migrate_calc_types(apps, schema_editor):
    """Перенос старых способов расчёта в calc_type.

    - use_custom_formula + 'BASE*FACTOR' → percent_of_base (base_amount=BASE, percent=FACTOR);
    - use_custom_formula + прочее → manual (цена уже посчитана, оставляем как есть);
    - percent без формулы → percent_of_contract;
    - иначе → manual.
    """
    ContractPayments = apps.get_model('ProjectContract', 'ContractPayments')
    unparsed = []
    for p in ContractPayments.objects.all().iterator():
        if getattr(p, 'use_custom_formula', False):
            m = _SIMPLE_FORMULA.match(p.custom_formula or '')
            if m:
                p.calc_type = 'percent_of_base'
                p.base_amount = Decimal(m.group(1))
                p.percent = float(m.group(2))
            else:
                p.calc_type = 'manual'
                unparsed.append(p.id)
        elif p.percent is not None:
            p.calc_type = 'percent_of_contract'
        else:
            p.calc_type = 'manual'
        p.save(update_fields=['calc_type', 'base_amount', 'percent'])
    if unparsed:
        print(f'WARNING 0003: формулы не распознаны, оставлены manual: {unparsed}')


def reverse_calc_types(apps, schema_editor):
    ContractPayments = apps.get_model('ProjectContract', 'ContractPayments')
    ContractPayments.objects.all().update(use_custom_formula=False)


class Migration(migrations.Migration):

    dependencies = [
        ('ProjectContract', '0002_remove_contract_sub_project'),
    ]

    operations = [
        migrations.AddField(
            model_name='contractpayments',
            name='calc_type',
            field=models.CharField(choices=[('manual', 'Вручную (фиксированная цена)'), ('percent_of_contract', 'Доля от цены договора'), ('percent_of_base', 'Доля от фиксированной суммы')], default='manual', max_length=30, verbose_name='Тип расчёта цены'),
        ),
        migrations.AddField(
            model_name='contractpayments',
            name='base_amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Сумма-база для доли'),
        ),
        migrations.RunPython(migrate_calc_types, reverse_calc_types),
        migrations.RemoveField(
            model_name='contractpayments',
            name='custom_formula',
        ),
        migrations.RemoveField(
            model_name='contractpayments',
            name='field_to_overwrite',
        ),
        migrations.RemoveField(
            model_name='contractpayments',
            name='use_custom_formula',
        ),
        migrations.AlterField(
            model_name='contractpayments',
            name='percent',
            field=models.FloatField(blank=True, null=True, verbose_name='доля (0..1)'),
        ),
    ]
