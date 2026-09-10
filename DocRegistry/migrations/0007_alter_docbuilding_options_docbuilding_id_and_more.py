# Смена PK Зданий (code → id) + проектный скоуп + stamp подписанта.
#
# Порядок важен для SQLite: сначала снимаем зависимые FK (иначе
# "foreign key mismatch" при rebuild таблицы), затем меняем PK,
# затем возвращаем FK пустыми — реимпорт всё восстановит по кодам.
# id записей реестра стабильны (строки не удаляются).
import django.db.models.deletion
from django.db import migrations, models


def _backfill_m1(apps, schema_editor):
    DocBuilding = apps.get_model('DocRegistry', 'DocBuilding')
    DocProject = apps.get_model('DocRegistry', 'DocProject')
    m1, _ = DocProject.objects.get_or_create(
        code='M1', defaults={'name': 'Волоколамск'})
    DocBuilding.objects.filter(project__isnull=True).update(project=m1)


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('DocRegistry', '0006_docproject_docregisterentry_project'),
    ]

    operations = [
        # 1. снять зависимые FK
        migrations.RemoveField(model_name='docregisterentry', name='building'),
        migrations.RemoveField(model_name='docregisterentry', name='building_no'),
        migrations.RemoveField(model_name='docsigner', name='building'),
        # 2. смена PK + скоуп + stamp
        migrations.AlterModelOptions(
            name='docbuilding',
            options={'ordering': ['project__code', 'code'], 'verbose_name': 'Здание (справочник РД)', 'verbose_name_plural': 'Здания (справочник РД)'},
        ),
        migrations.AddField(
            model_name='docbuilding',
            name='id',
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
        ),
        migrations.AddField(
            model_name='docbuilding',
            name='project',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='buildings', to='DocRegistry.docproject', verbose_name='Проект'),
        ),
        migrations.AddField(
            model_name='docsigner',
            name='stamp',
            field=models.BooleanField(default=False, help_text='В ячейке подписи — штамп СОГЛАСОВАНО + ФИО + дата/время (как э-подпись)', verbose_name='Штамп «Согласовано»'),
        ),
        migrations.AlterField(
            model_name='docbuilding',
            name='code',
            field=models.IntegerField(db_index=True, verbose_name='Код здания'),
        ),
        migrations.AddConstraint(
            model_name='docbuilding',
            constraint=models.UniqueConstraint(fields=('project', 'code'), name='docbuilding_project_code_unique'),
        ),
        # 3. вернуть FK пустыми + проект М1 зданиям
        migrations.AddField(
            model_name='docregisterentry',
            name='building',
            field=models.ForeignKey(blank=True, help_text='accdb: Наименование здания (код)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='entries', to='DocRegistry.docbuilding', verbose_name='Наименование здания'),
        ),
        migrations.AddField(
            model_name='docregisterentry',
            name='building_no',
            field=models.ForeignKey(blank=True, help_text='accdb: Номер здания (код)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='entries_by_number', to='DocRegistry.docbuilding', verbose_name='Номер здания'),
        ),
        migrations.AddField(
            model_name='docsigner',
            name='building',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='signers', to='DocRegistry.docbuilding', verbose_name='Здание (не используется резолвом)'),
        ),
        migrations.RunPython(_backfill_m1, _noop),
    ]
