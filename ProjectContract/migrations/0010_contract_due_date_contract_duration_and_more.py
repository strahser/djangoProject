# Generated by Django 5.0.4 on 2025-01-16 06:58

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ProjectContract', '0009_alter_concretepaymentcalendar_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='due_date',
            field=models.DateField(blank=True, default=datetime.date.today, null=True, verbose_name='план.завершение'),
        ),
        migrations.AddField(
            model_name='contract',
            name='duration',
            field=models.FloatField(blank=True, default=1, null=True, verbose_name='длительность'),
        ),
        migrations.AddField(
            model_name='contract',
            name='start_date',
            field=models.DateField(blank=True, default=datetime.date.today, null=True, verbose_name='план.начало'),
        ),
    ]
