# Generated by Django 5.0.4 on 2024-08-19 14:15

import django.db.models.deletion
import tinymce.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('ProjectContract', '0001_initial'),
        ('StaticData', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Task',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, verbose_name='Наименование Задачи')),
                ('description', tinymce.models.HTMLField(blank=True, null=True, verbose_name='Описание')),
                ('price', models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=12, null=True, verbose_name='цена')),
                ('due_date', models.DateField(blank=True, null=True, verbose_name='завершение')),
                ('creation_stamp', models.DateTimeField(auto_now_add=True, verbose_name='дата создания')),
                ('update_stamp', models.DateTimeField(auto_now=True, verbose_name='дата изменения')),
                ('building_number', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='StaticData.buildingnumber', verbose_name='Здание')),
                ('category', models.ForeignKey(blank=True, default=1, null=True, on_delete=django.db.models.deletion.SET_NULL, to='StaticData.category', verbose_name='Категория')),
                ('contract', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='ProjectContract.contract', verbose_name='Договор')),
                ('contractor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='ProjectContract.contractor', verbose_name='Ответсвенный')),
                ('design_chapter', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='StaticData.designchapter', verbose_name='Раздел')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tasks', to=settings.AUTH_USER_MODEL, verbose_name='Владелец')),
                ('project_site', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='StaticData.projectsite', verbose_name='Проект')),
                ('status', models.ForeignKey(blank=True, default=1, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='StaticData.status', verbose_name='Статус')),
                ('sub_project', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='StaticData.subproject', verbose_name='Подпроект')),
            ],
            options={
                'verbose_name': 'Задача',
                'verbose_name_plural': 'Задачи',
            },
        ),
        migrations.CreateModel(
            name='SubTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, max_length=256, null=True, verbose_name='Подзадача')),
                ('description', models.TextField(blank=True, null=True, verbose_name='Описание')),
                ('price', models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True, verbose_name='цена')),
                ('creation_stamp', models.DateTimeField(auto_now_add=True, verbose_name='дата создания')),
                ('update_stamp', models.DateTimeField(auto_now=True, verbose_name='дата изменения')),
                ('due_date', models.DateField(blank=True, null=True, verbose_name='дата завершения')),
                ('parent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='ProjectTDL.task', verbose_name='Наим. Задачи')),
            ],
            options={
                'verbose_name': 'Подзадача',
                'verbose_name_plural': 'Подзадачи',
            },
        ),
        migrations.CreateModel(
            name='Email',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uid', models.CharField(blank=True, max_length=200, null=True, verbose_name='uid')),
                ('email_type', models.CharField(choices=[('IN', 'Входящие'), ('OUT', 'Исходящие')], default=('IN', 'Входящие'), max_length=10, verbose_name='Тип Сообщения')),
                ('name', models.CharField(blank=True, max_length=100, null=True, verbose_name='Наименование')),
                ('link', models.CharField(blank=True, max_length=300, null=True, verbose_name='Ссылка')),
                ('subject', models.CharField(blank=True, max_length=300, null=True, verbose_name='Тема письма')),
                ('body', tinymce.models.HTMLField(blank=True, null=True, verbose_name='Тело письма')),
                ('sender', models.CharField(blank=True, max_length=300, null=True, verbose_name='Отправитель')),
                ('receiver', models.CharField(blank=True, max_length=300, null=True, verbose_name='Получатель')),
                ('email_stamp', models.DateTimeField(blank=True, null=True, verbose_name='дата письма')),
                ('creation_stamp', models.DateTimeField(auto_now_add=True, null=True, verbose_name='дата создания')),
                ('update_stamp', models.DateTimeField(auto_now=True, null=True, verbose_name='дата изменения')),
                ('building_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='StaticData.buildingtype', verbose_name='Здание')),
                ('category', models.ForeignKey(blank=True, default=1, null=True, on_delete=django.db.models.deletion.SET_NULL, to='StaticData.category', verbose_name='Категория')),
                ('contractor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='ProjectContract.contractor', verbose_name='Подрядчик')),
                ('project_site', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='StaticData.projectsite', verbose_name='Проект')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='ProjectTDL.task', verbose_name='Род. Задача')),
            ],
            options={
                'verbose_name': 'E-mail',
                'verbose_name_plural': 'E-mail',
                'ordering': ['-email_stamp'],
            },
        ),
    ]
