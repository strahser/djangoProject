# Generated by Django 5.0.4 on 2024-11-08 14:07

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ProjectContract', '0006_contractpayments_payment_description_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contractor',
            name='name',
            field=models.CharField(max_length=200, null=True, verbose_name='Подрядчик'),
        ),
        migrations.AlterField(
            model_name='contractpayments',
            name='name',
            field=models.TextField(null=True, verbose_name='Наименование платежа'),
        ),
        migrations.AlterField(
            model_name='contractpayments',
            name='parent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='ProjectContract.contractpayments', verbose_name='Зависимость'),
        ),
    ]
