"""Разделение «один объект — один реестр».

Схема: DocBuildingType (общий справочник типов) + FK на зданиях;
project обязателен (запись PROTECT, здание CASCADE); уникальность кода
записи — в рамках проекта (project, code); порядок — по проекту и коду.
Данные: типы выводятся из наименований (часть до «№»), линкуем здания.
"""
from __future__ import annotations

import re

from django.db import migrations, models
import django.db.models.deletion


def _type_name(building_name: str) -> str:
    name = (building_name or '').strip()
    if not name:
        return ''
    return re.sub(r'\s*№.*$', '', name).strip() or name


def backfill_types(apps, schema_editor):
    DocBuilding = apps.get_model('DocRegistry', 'DocBuilding')
    DocBuildingType = apps.get_model('DocRegistry', 'DocBuildingType')
    names = sorted({b.name for b in DocBuilding.objects.all() if (b.name or '').strip()})
    type_names = sorted({_type_name(n) for n in names if _type_name(n)})
    type_ids = {}
    for i, tname in enumerate(type_names, start=1):
        t, _ = DocBuildingType.objects.get_or_create(code=i, defaults={'name': tname})
        type_ids[t.name] = t.pk
    linked = 0
    for b in DocBuilding.objects.all():
        tname = _type_name(b.name)
        if tname and tname in type_ids and b.building_type_id != type_ids[tname]:
            b.building_type_id = type_ids[tname]
            b.save(update_fields=['building_type'])
            linked += 1
    if linked:
        print(f'Типы зданий: {len(type_ids)}, прилинковано зданий: {linked}')


def unbackfill_types(apps, schema_editor):
    DocBuildingType = apps.get_model('DocRegistry', 'DocBuildingType')
    DocBuildingType.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('DocRegistry', '0007_alter_docbuilding_options_docbuilding_id_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocBuildingType',
            fields=[
                ('code', models.IntegerField(primary_key=True, serialize=False, verbose_name='Код типа')),
                ('name', models.CharField(max_length=200, verbose_name='Тип здания')),
            ],
            options={
                'verbose_name': 'Тип здания (общий справочник)',
                'verbose_name_plural': 'Типы зданий (общий справочник)',
                'ordering': ['code'],
            },
        ),
        migrations.AddField(
            model_name='docbuilding',
            name='building_type',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='buildings', to='DocRegistry.docbuildingtype',
                verbose_name='Тип здания',
                help_text='Общий для всех объектов (коровник, телятник…); номер — свой у проекта'),
        ),
        migrations.AlterField(
            model_name='docbuilding',
            name='project',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='buildings', to='DocRegistry.docproject',
                verbose_name='Проект (объект)'),
        ),
        migrations.AlterField(
            model_name='docregisterentry',
            name='code',
            field=models.PositiveIntegerField(
                verbose_name='Код',
                help_text='accdb: код (нумерация своя у каждого проекта)'),
        ),
        migrations.AlterField(
            model_name='docregisterentry',
            name='project',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='entries', to='DocRegistry.docproject',
                verbose_name='Проект (объект)',
                help_text='Реестр принадлежит объекту; смена запрещена удалением проекта'),
        ),
        migrations.AlterModelOptions(
            name='docregisterentry',
            options={
                'ordering': ['project__code', 'code'],
                'verbose_name': 'Запись реестра РД',
                'verbose_name_plural': 'Реестр РД',
            },
        ),
        migrations.AddConstraint(
            model_name='docregisterentry',
            constraint=models.UniqueConstraint(
                fields=('project', 'code'), name='docentry_project_code_unique'),
        ),
        migrations.RunPython(backfill_types, unbackfill_types),
    ]
