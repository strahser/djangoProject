# Generated for Ф1 рефакторинга: статусы, заказчик, субподряды, факт оплат, журнал.
from django.db import migrations, models


def backfill_payment_status(apps, schema_editor):
    ContractPayments = apps.get_model('ProjectContract', 'ContractPayments')
    paid = ContractPayments.objects.filter(made_payment=True)
    n_paid = paid.count()
    for p in paid.iterator():
        p.status = 'paid'
        if p.paid_amount is None:
            p.paid_amount = p.price
        p.save(update_fields=['status', 'paid_amount'])
    n_planned = ContractPayments.objects.filter(made_payment=False)\
        .update(status='planned')
    print(f'0004: paid={n_paid}, planned={n_planned}')


def reverse_payment_status(apps, schema_editor):
    ContractPayments = apps.get_model('ProjectContract', 'ContractPayments')
    ContractPayments.objects.filter(status='paid').update(made_payment=True)
    ContractPayments.objects.exclude(status='paid').update(made_payment=False)


class Migration(migrations.Migration):

    dependencies = [
        ('ProjectContract', '0003_typed_price_calc'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='client',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='client_contracts', to='ProjectContract.contractor', verbose_name='Заказчик'),
        ),
        migrations.AddField(
            model_name='contract',
            name='number',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Номер договора'),
        ),
        migrations.AddField(
            model_name='contract',
            name='parent',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='children', to='ProjectContract.contract', verbose_name='Головной договор (субподряд)'),
        ),
        migrations.AddField(
            model_name='contract',
            name='sign_date',
            field=models.DateField(blank=True, null=True, verbose_name='Дата подписания'),
        ),
        migrations.AddField(
            model_name='contract',
            name='status',
            field=models.CharField(choices=[('draft', 'Черновик'), ('active', 'Действующий'), ('suspended', 'Приостановлен'), ('closed', 'Завершён'), ('canceled', 'Расторгнут')], default='active', max_length=20, verbose_name='Статус'),
        ),
        migrations.AddField(
            model_name='contractpayments',
            name='invoice_number',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Номер счёта'),
        ),
        migrations.AddField(
            model_name='contractpayments',
            name='paid_amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Оплачено (факт)'),
        ),
        migrations.AddField(
            model_name='contractpayments',
            name='paid_date',
            field=models.DateField(blank=True, null=True, verbose_name='Дата оплаты (факт)'),
        ),
        migrations.AddField(
            model_name='contractpayments',
            name='status',
            field=models.CharField(choices=[('planned', 'Запланирован'), ('guaranteed', 'Гарантирован'), ('high_prob', 'Высокая вероятность'), ('low_prob', 'Низкая вероятность'), ('approved', 'Согласован'), ('invoiced', 'Выставлен счёт'), ('partially_paid', 'Частично оплачен'), ('paid', 'Оплачен')], default='planned', max_length=20, verbose_name='Статус'),
        ),
        migrations.AlterField(
            model_name='contractpayments',
            name='calc_type',
            field=models.CharField(choices=[('manual', 'Вручную (фиксированная цена)'), ('percent_of_contract', 'Доля от цены договора'), ('percent_of_base', 'Доля от фиксированной суммы'), ('percent_of_parent', 'Доля от родительского платежа')], default='manual', max_length=30, verbose_name='Тип расчёта цены'),
        ),
        migrations.CreateModel(
            name='ContractChangeLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('creation_stamp', models.DateTimeField(auto_now_add=True, null=True, verbose_name='дата создания')),
                ('update_stamp', models.DateTimeField(auto_now=True, null=True, verbose_name='дата изменения')),
                ('action', models.CharField(max_length=50, verbose_name='Действие')),
                ('details', models.TextField(blank=True, default='', verbose_name='Подробности')),
                ('contract', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='change_logs', to='ProjectContract.contract', verbose_name='Договор')),
                ('payment', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='change_logs', to='ProjectContract.contractpayments', verbose_name='Платёж')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, to='auth.User', verbose_name='Кто')),
            ],
            options={
                'verbose_name': 'Изменение договора/платежа',
                'verbose_name_plural': 'Журнал изменений',
                'ordering': ['-creation_stamp', '-id'],
            },
        ),
        migrations.RunPython(backfill_payment_status, reverse_payment_status),
    ]
