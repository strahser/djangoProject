"""Тип здания — в общий справочник StaticData: FK зданий М1/К1 переведены на
StaticData.BuildingType, DocBuildingType удалён.

Слияние по наименованию: совпавшие — переиспользуются (почта/задачи их уже
знают), недостающие — создаются. Ремап через отрицательные id во избежание
коллизий со старыми кодами.
"""
from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


def merge_types(apps, schema_editor):
    OldType = apps.get_model('DocRegistry', 'DocBuildingType')
    NewType = apps.get_model('StaticData', 'BuildingType')
    mapping = {}
    for old in OldType.objects.all():
        new, _ = NewType.objects.get_or_create(name=old.name)
        mapping[old.code] = new.pk
    print(f'Типы: старых {len(mapping)}, всего в справочнике {NewType.objects.count()}')
    for label in ('M1Building', 'K1Building'):
        B = apps.get_model('DocRegistry', label)
        moved = 0
        B.objects.exclude(building_type__isnull=True).update(
            building_type=models.F('building_type') * -1)
        for old_code, new_id in mapping.items():
            moved += B.objects.filter(building_type_id=-old_code).update(
                building_type_id=new_id)
        left = B.objects.exclude(building_type__isnull=True).count()
        print(f'{label}: перелинковано {moved}, осталось {left}')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('DocRegistry', '0012_alter_k1issue_approval_pdf_alter_k1issue_waybill_pdf_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='m1building',
            name='building_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='StaticData.buildingtype', verbose_name='Тип здания', help_text='Общий справочник (Справочники → Здания Тип); номер — свой у объекта'),
        ),
        migrations.AlterField(
            model_name='k1building',
            name='building_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='StaticData.buildingtype', verbose_name='Тип здания', help_text='Общий справочник (Справочники → Здания Тип); номер — свой у объекта'),
        ),
        migrations.RunPython(merge_types, noop),
        migrations.DeleteModel(name='DocBuildingType'),
    ]
