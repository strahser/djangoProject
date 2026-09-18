"""Физическое разделение реестров: абстрактные базы + таблицы doc_m1_*/doc_k1_*.

Данные М1 переносятся 1:1 с сохранением id (FK целы); таблицы К1 остаются
пустыми до импорта К1.accdb. Старые общие таблицы удаляются.
"""
from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


def _copy_table(apps, old_name, new_name):
    Old = apps.get_model('DocRegistry', old_name)
    New = apps.get_model('DocRegistry', new_name)
    new_attnames = [f.attname for f in New._meta.local_fields]
    old_attnames = {f.attname for f in Old._meta.local_fields}
    common = [n for n in new_attnames if n in old_attnames]
    n = 0
    for row in Old.objects.values(*common).order_by('id'):
        New.objects.create(**row)
        n += 1
    print(f'{old_name} → {new_name}: {n}')


def copy_m1_data(apps, schema_editor):
    for old, new in (
        ('DocBuilding', 'M1Building'),
        ('DocRegisterEntry', 'M1Entry'),
        ('DocRevision', 'M1Revision'),
        ('DocCheck', 'M1Check'),
        ('DocRemark', 'M1Remark'),
        ('DocIssue', 'M1Issue'),
        ('DocChangeLog', 'M1ChangeLog'),
    ):
        _copy_table(apps, old, new)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('DocRegistry', '0009_alter_docsigner_building'),
    ]

    operations = [
        migrations.CreateModel(
            name='M1Building',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.IntegerField(db_index=True, unique=True, verbose_name='Код здания')),
                ('number', models.CharField(blank=True, default='', max_length=20, verbose_name='№ здания')),
                ('name', models.CharField(blank=True, default='', max_length=200, verbose_name='Наименование здания')),
                ('building_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='DocRegistry.docbuildingtype', verbose_name='Тип здания', help_text='Общий для всех объектов (коровник, телятник…); номер — свой у объекта')),
            ],
            options={'db_table': 'doc_m1_building', 'verbose_name': 'Здание М1', 'verbose_name_plural': 'Здания М1', 'ordering': ['code']},
        ),
        migrations.CreateModel(
            name='K1Building',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.IntegerField(db_index=True, unique=True, verbose_name='Код здания')),
                ('number', models.CharField(blank=True, default='', max_length=20, verbose_name='№ здания')),
                ('name', models.CharField(blank=True, default='', max_length=200, verbose_name='Наименование здания')),
                ('building_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='DocRegistry.docbuildingtype', verbose_name='Тип здания', help_text='Общий для всех объектов (коровник, телятник…); номер — свой у объекта')),
            ],
            options={'db_table': 'doc_k1_building', 'verbose_name': 'Здание К1', 'verbose_name_plural': 'Здания К1', 'ordering': ['code']},
        ),
        migrations.CreateModel(
            name='M1Entry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.PositiveIntegerField(help_text='accdb: код', unique=True, verbose_name='Код')),
                ('cipher', models.CharField(blank=True, db_index=True, default='', help_text='accdb: шифр', max_length=200, verbose_name='Шифр')),
                ('file_name', models.CharField(blank=True, default='', help_text='accdb: Назв Эл файла (max 771 в live)', max_length=1000, verbose_name='Имя эл. файла')),
                ('approval_status', models.CharField(blank=True, default='', help_text='accdb: согласование', max_length=50, verbose_name='Согласование')),
                ('approval_date', models.DateField(blank=True, help_text='accdb: дата согласования', null=True, verbose_name='Дата согласования')),
                ('submitted_flag', models.CharField(blank=True, default='', help_text='accdb: подано на согласование', max_length=10, verbose_name='Подано')),
                ('change_descr', models.TextField(blank=True, default='', help_text='accdb: Описание изм', verbose_name='Описание изменений')),
                ('submit_date', models.DateField(blank=True, help_text='accdb: Дата подачи на согласование', null=True, verbose_name='Дата подачи')),
                ('acts', models.CharField(blank=True, default='', help_text='accdb: Акты (max 289 в live)', max_length=500, verbose_name='Акты')),
                ('accdb_row_hash', models.CharField(blank=True, default='', help_text='sha1 конкатенации полей — для ночного check_accdb_drift (DOC-5)', max_length=64, verbose_name='Хеш строки accdb')),
                ('building', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='entries', to='DocRegistry.m1building', verbose_name='Наименование здания', help_text='accdb: Наименование здания (код)')),
                ('building_no', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='entries_by_number', to='DocRegistry.m1building', verbose_name='Номер здания', help_text='accdb: Номер здания (код)')),
                ('contract', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='ProjectContract.contract', verbose_name='Договор')),
                ('developer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='DocRegistry.docdeveloper', verbose_name='Разраб.', help_text='accdb: разраб_нов (код)')),
                ('section', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='DocRegistry.docsection', verbose_name='Раздел', help_text='accdb: раздел (код)')),
            ],
            options={'db_table': 'doc_m1_entry', 'verbose_name': 'Запись реестра М1', 'verbose_name_plural': 'Реестр М1', 'ordering': ['code']},
        ),
        migrations.CreateModel(
            name='K1Entry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.PositiveIntegerField(help_text='accdb: код', unique=True, verbose_name='Код')),
                ('cipher', models.CharField(blank=True, db_index=True, default='', help_text='accdb: шифр', max_length=200, verbose_name='Шифр')),
                ('file_name', models.CharField(blank=True, default='', help_text='accdb: Назв Эл файла (max 771 в live)', max_length=1000, verbose_name='Имя эл. файла')),
                ('approval_status', models.CharField(blank=True, default='', help_text='accdb: согласование', max_length=50, verbose_name='Согласование')),
                ('approval_date', models.DateField(blank=True, help_text='accdb: дата согласования', null=True, verbose_name='Дата согласования')),
                ('submitted_flag', models.CharField(blank=True, default='', help_text='accdb: подано на согласование', max_length=10, verbose_name='Подано')),
                ('change_descr', models.TextField(blank=True, default='', help_text='accdb: Описание изм', verbose_name='Описание изменений')),
                ('submit_date', models.DateField(blank=True, help_text='accdb: Дата подачи на согласование', null=True, verbose_name='Дата подачи')),
                ('acts', models.CharField(blank=True, default='', help_text='accdb: Акты (max 289 в live)', max_length=500, verbose_name='Акты')),
                ('accdb_row_hash', models.CharField(blank=True, default='', help_text='sha1 конкатенации полей — для ночного check_accdb_drift (DOC-5)', max_length=64, verbose_name='Хеш строки accdb')),
                ('building', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='entries', to='DocRegistry.k1building', verbose_name='Наименование здания', help_text='accdb: Наименование здания (код)')),
                ('building_no', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='entries_by_number', to='DocRegistry.k1building', verbose_name='Номер здания', help_text='accdb: Номер здания (код)')),
                ('contract', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='ProjectContract.contract', verbose_name='Договор')),
                ('developer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='DocRegistry.docdeveloper', verbose_name='Разраб.', help_text='accdb: разраб_нов (код)')),
                ('section', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='DocRegistry.docsection', verbose_name='Раздел', help_text='accdb: раздел (код)')),
            ],
            options={'db_table': 'doc_k1_entry', 'verbose_name': 'Запись реестра К1', 'verbose_name_plural': 'Реестр К1', 'ordering': ['code']},
        ),
        migrations.CreateModel(
            name='M1Revision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rev_no', models.PositiveIntegerField(default=1, verbose_name='№ ревизии')),
                ('file', models.FileField(blank=True, null=True, upload_to='DocRegistry/incoming/%Y/%m/', verbose_name='Файл ревизии')),
                ('sha256', models.CharField(blank=True, default='', max_length=64, verbose_name='SHA-256')),
                ('size', models.PositiveIntegerField(default=0, verbose_name='Размер (байт)')),
                ('received_at', models.DateTimeField(auto_now_add=True, verbose_name='Получена')),
                ('source', models.CharField(choices=[('email', 'Из письма'), ('yadi', 'Yandex.Disk ссылка'), ('manual', 'Вручную')], default='manual', max_length=10, verbose_name='Источник')),
                ('status', models.CharField(choices=[('received', 'Получена'), ('validating', 'На проверке'), ('checked_ok', 'Проверена'), ('has_remarks', 'Замечания'), ('registered', 'В реестре'), ('issued', 'Выдана в ПР')], default='received', max_length=12, verbose_name='Статус')),
                ('storage_path', models.CharField(blank=True, default='', max_length=500, verbose_name='Путь выдачи (сеть)')),
                ('archive_path', models.CharField(blank=True, default='', max_length=500, verbose_name='Путь в архиве')),
                ('submitted_folder', models.CharField(blank=True, default='', max_length=300, verbose_name='Папка Подано')),
                ('accdb_task_code', models.CharField(blank=True, default='', help_text='[02 Задачи].Код задачи до маппинга на TaskNode (DOC-5)', max_length=20, verbose_name='Код задачи accdb')),
                ('attachment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='Emails.attachment', verbose_name='Вложение')),
                ('email', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='Emails.email', verbose_name='Письмо')),
                ('entry', models.ForeignKey(blank=True, help_text='Пусто до шага 3 (register) — приём идёт раньше привязки к реестру', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revisions', to='DocRegistry.m1entry', verbose_name='Запись реестра')),
                ('task', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='ProjectTDL.tasknode', verbose_name='Задача')),
            ],
            options={'db_table': 'doc_m1_revision', 'verbose_name': 'Ревизия М1', 'verbose_name_plural': 'Ревизии М1', 'ordering': ['entry__code', 'rev_no']},
        ),
        migrations.CreateModel(
            name='K1Revision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rev_no', models.PositiveIntegerField(default=1, verbose_name='№ ревизии')),
                ('file', models.FileField(blank=True, null=True, upload_to='DocRegistry/incoming/%Y/%m/', verbose_name='Файл ревизии')),
                ('sha256', models.CharField(blank=True, default='', max_length=64, verbose_name='SHA-256')),
                ('size', models.PositiveIntegerField(default=0, verbose_name='Размер (байт)')),
                ('received_at', models.DateTimeField(auto_now_add=True, verbose_name='Получена')),
                ('source', models.CharField(choices=[('email', 'Из письма'), ('yadi', 'Yandex.Disk ссылка'), ('manual', 'Вручную')], default='manual', max_length=10, verbose_name='Источник')),
                ('status', models.CharField(choices=[('received', 'Получена'), ('validating', 'На проверке'), ('checked_ok', 'Проверена'), ('has_remarks', 'Замечания'), ('registered', 'В реестре'), ('issued', 'Выдана в ПР')], default='received', max_length=12, verbose_name='Статус')),
                ('storage_path', models.CharField(blank=True, default='', max_length=500, verbose_name='Путь выдачи (сеть)')),
                ('archive_path', models.CharField(blank=True, default='', max_length=500, verbose_name='Путь в архиве')),
                ('submitted_folder', models.CharField(blank=True, default='', max_length=300, verbose_name='Папка Подано')),
                ('accdb_task_code', models.CharField(blank=True, default='', help_text='[02 Задачи].Код задачи до маппинга на TaskNode (DOC-5)', max_length=20, verbose_name='Код задачи accdb')),
                ('attachment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='Emails.attachment', verbose_name='Вложение')),
                ('email', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='Emails.email', verbose_name='Письмо')),
                ('entry', models.ForeignKey(blank=True, help_text='Пусто до шага 3 (register) — приём идёт раньше привязки к реестру', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revisions', to='DocRegistry.k1entry', verbose_name='Запись реестра')),
                ('task', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='ProjectTDL.tasknode', verbose_name='Задача')),
            ],
            options={'db_table': 'doc_k1_revision', 'verbose_name': 'Ревизия К1', 'verbose_name_plural': 'Ревизии К1', 'ordering': ['entry__code', 'rev_no']},
        ),
        migrations.AddConstraint(
            model_name='m1revision',
            constraint=models.UniqueConstraint(fields=('entry', 'rev_no'), name='doc_m1_rev_unique'),
        ),
        migrations.AddConstraint(
            model_name='k1revision',
            constraint=models.UniqueConstraint(fields=('entry', 'rev_no'), name='doc_k1_rev_unique'),
        ),
        migrations.CreateModel(
            name='M1Check',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('verdict', models.CharField(choices=[('PASS', 'Годно'), ('FAIL', 'Замечания')], max_length=4, verbose_name='Вердикт')),
                ('diff_json', models.JSONField(blank=True, default=dict, help_text='листы/штампы/размеры из revision_diff', verbose_name='Что изменилось')),
                ('checks_json', models.JSONField(blank=True, default=dict, verbose_name='Проверки П1–П4')),
                ('questions_md', models.TextField(blank=True, default='', verbose_name='Вопросы подрядчику')),
                ('checked_at', models.DateTimeField(auto_now=True, verbose_name='Проверено')),
                ('checked_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user', verbose_name='Проверил')),
                ('revision', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='validation', to='DocRegistry.m1revision', verbose_name='Ревизия')),
            ],
            options={'db_table': 'doc_m1_check', 'verbose_name': 'Проверка М1', 'verbose_name_plural': 'Проверки М1'},
        ),
        migrations.CreateModel(
            name='K1Check',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('verdict', models.CharField(choices=[('PASS', 'Годно'), ('FAIL', 'Замечания')], max_length=4, verbose_name='Вердикт')),
                ('diff_json', models.JSONField(blank=True, default=dict, help_text='листы/штампы/размеры из revision_diff', verbose_name='Что изменилось')),
                ('checks_json', models.JSONField(blank=True, default=dict, verbose_name='Проверки П1–П4')),
                ('questions_md', models.TextField(blank=True, default='', verbose_name='Вопросы подрядчику')),
                ('checked_at', models.DateTimeField(auto_now=True, verbose_name='Проверено')),
                ('checked_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user', verbose_name='Проверил')),
                ('revision', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='validation', to='DocRegistry.k1revision', verbose_name='Ревизия')),
            ],
            options={'db_table': 'doc_k1_check', 'verbose_name': 'Проверка К1', 'verbose_name_plural': 'Проверки К1'},
        ),
        migrations.CreateModel(
            name='M1Remark',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(verbose_name='Текст замечания')),
                ('author', models.CharField(blank=True, default='', max_length=200, verbose_name='Автор')),
                ('remark_date', models.DateField(blank=True, null=True, verbose_name='Дата замечания')),
                ('sheet_pdf', models.FileField(blank=True, null=True, upload_to='DocRegistry/remarks/%Y/%m/', verbose_name='Лист согласования (PDF)')),
                ('sent_at', models.DateTimeField(blank=True, null=True, verbose_name='Отправлено')),
                ('reply_at', models.DateTimeField(blank=True, null=True, verbose_name='Ответ получен')),
                ('reply_file', models.FileField(blank=True, null=True, upload_to='DocRegistry/remarks/%Y/%m/', verbose_name='Ответ подрядчика')),
                ('entry', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='history_remarks', to='DocRegistry.m1entry', verbose_name='Запись реестра (история)')),
                ('revision', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='remarks', to='DocRegistry.m1revision', verbose_name='Ревизия')),
            ],
            options={'db_table': 'doc_m1_remark', 'verbose_name': 'Замечание М1', 'verbose_name_plural': 'Замечания М1', 'ordering': ['-id']},
        ),
        migrations.CreateModel(
            name='K1Remark',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(verbose_name='Текст замечания')),
                ('author', models.CharField(blank=True, default='', max_length=200, verbose_name='Автор')),
                ('remark_date', models.DateField(blank=True, null=True, verbose_name='Дата замечания')),
                ('sheet_pdf', models.FileField(blank=True, null=True, upload_to='DocRegistry/remarks/%Y/%m/', verbose_name='Лист согласования (PDF)')),
                ('sent_at', models.DateTimeField(blank=True, null=True, verbose_name='Отправлено')),
                ('reply_at', models.DateTimeField(blank=True, null=True, verbose_name='Ответ получен')),
                ('reply_file', models.FileField(blank=True, null=True, upload_to='DocRegistry/remarks/%Y/%m/', verbose_name='Ответ подрядчика')),
                ('entry', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='history_remarks', to='DocRegistry.k1entry', verbose_name='Запись реестра (история)')),
                ('revision', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='remarks', to='DocRegistry.k1revision', verbose_name='Ревизия')),
            ],
            options={'db_table': 'doc_k1_remark', 'verbose_name': 'Замечание К1', 'verbose_name_plural': 'Замечания К1', 'ordering': ['-id']},
        ),
        migrations.CreateModel(
            name='M1Issue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('waybill_no', models.CharField(max_length=50, verbose_name='№ накладной')),
                ('waybill_date', models.DateField(blank=True, null=True, verbose_name='Дата накладной')),
                ('waybill_pdf', models.FileField(blank=True, null=True, upload_to='DocRegistry/issues/%Y/%m/', verbose_name='Накладная (PDF)')),
                ('network_path', models.CharField(blank=True, default='', max_length=500, verbose_name='Папка выдачи (сеть)')),
                ('approval_pdf', models.FileField(blank=True, null=True, upload_to='DocRegistry/issues/%Y/%m/', verbose_name='Лист согласования (PDF)')),
                ('archived_old_rev', models.BooleanField(default=False, verbose_name='Старая ревизия убрана в архив')),
                ('issued_at', models.DateTimeField(auto_now_add=True, verbose_name='Выдано')),
                ('entry', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='issues', to='DocRegistry.m1entry', verbose_name='Запись реестра')),
                ('issued_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user', verbose_name='Выдал')),
            ],
            options={'db_table': 'doc_m1_issue', 'verbose_name': 'Выдача М1', 'verbose_name_plural': 'Выдачи М1', 'ordering': ['-issued_at']},
        ),
        migrations.CreateModel(
            name='K1Issue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('waybill_no', models.CharField(max_length=50, verbose_name='№ накладной')),
                ('waybill_date', models.DateField(blank=True, null=True, verbose_name='Дата накладной')),
                ('waybill_pdf', models.FileField(blank=True, null=True, upload_to='DocRegistry/issues/%Y/%m/', verbose_name='Накладная (PDF)')),
                ('network_path', models.CharField(blank=True, default='', max_length=500, verbose_name='Папка выдачи (сеть)')),
                ('approval_pdf', models.FileField(blank=True, null=True, upload_to='DocRegistry/issues/%Y/%m/', verbose_name='Лист согласования (PDF)')),
                ('issued_at', models.DateTimeField(auto_now_add=True, verbose_name='Выдано')),
                ('entry', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='issues', to='DocRegistry.k1entry', verbose_name='Запись реестра')),
                ('issued_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user', verbose_name='Выдал')),
            ],
            options={'db_table': 'doc_k1_issue', 'verbose_name': 'Выдача К1', 'verbose_name_plural': 'Выдачи К1', 'ordering': ['-issued_at']},
        ),
        migrations.CreateModel(
            name='M1ChangeLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('field', models.CharField(max_length=100, verbose_name='Поле')),
                ('old_value', models.TextField(blank=True, default='', verbose_name='Было')),
                ('new_value', models.TextField(blank=True, default='', verbose_name='Стало')),
                ('changed_at', models.DateTimeField(auto_now_add=True, verbose_name='Когда')),
                ('source', models.CharField(choices=[('manual', 'Руками'), ('api', 'API агента'), ('import', 'Импорт accdb')], default='manual', max_length=10, verbose_name='Источник')),
                ('changed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user', verbose_name='Кто')),
                ('entry', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='changelog', to='DocRegistry.m1entry', verbose_name='Запись реестра')),
                ('revision', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='changelog', to='DocRegistry.m1revision', verbose_name='Ревизия')),
            ],
            options={'db_table': 'doc_m1_changelog', 'verbose_name': 'Запись журнала М1', 'verbose_name_plural': 'Журнал М1', 'ordering': ['-changed_at']},
        ),
        migrations.CreateModel(
            name='K1ChangeLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('field', models.CharField(max_length=100, verbose_name='Поле')),
                ('old_value', models.TextField(blank=True, default='', verbose_name='Было')),
                ('new_value', models.TextField(blank=True, default='', verbose_name='Стало')),
                ('changed_at', models.DateTimeField(auto_now_add=True, verbose_name='Когда')),
                ('source', models.CharField(choices=[('manual', 'Руками'), ('api', 'API агента'), ('import', 'Импорт accdb')], default='manual', max_length=10, verbose_name='Источник')),
                ('changed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user', verbose_name='Кто')),
                ('entry', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='changelog', to='DocRegistry.k1entry', verbose_name='Запись реестра')),
                ('revision', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='changelog', to='DocRegistry.k1revision', verbose_name='Ревизия')),
            ],
            options={'db_table': 'doc_k1_changelog', 'verbose_name': 'Запись журнала К1', 'verbose_name_plural': 'Журнал К1', 'ordering': ['-changed_at']},
        ),
        migrations.RunPython(copy_m1_data, noop),
        migrations.RemoveField(model_name='docsigner', name='building'),
        migrations.DeleteModel(name='DocChangeLog'),
        migrations.DeleteModel(name='DocCheck'),
        migrations.DeleteModel(name='DocIssue'),
        migrations.DeleteModel(name='DocRemark'),
        migrations.DeleteModel(name='DocRevision'),
        migrations.DeleteModel(name='DocRegisterEntry'),
        migrations.DeleteModel(name='DocBuilding'),
    ]
