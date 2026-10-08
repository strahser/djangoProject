"""Детальное описание изменений: change_descr (короткое, в таблицу) +
change_descr_detail (техническое, из листа изменений PDF — ниже таблицы листа согласования).
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('DocRegistry', '0013_building_type_to_staticdata'),
    ]

    operations = [
        migrations.AddField(
            model_name='m1entry',
            name='change_descr_detail',
            field=models.TextField(
                blank=True, default='',
                help_text='Технические изменения из листа изменений PDF — ниже таблицы листа согласования',
                verbose_name='Детальное описание изменений',
            ),
        ),
        migrations.AddField(
            model_name='k1entry',
            name='change_descr_detail',
            field=models.TextField(
                blank=True, default='',
                help_text='Технические изменения из листа изменений PDF — ниже таблицы листа согласования',
                verbose_name='Детальное описание изменений',
            ),
        ),
    ]
