from enum import Enum
import uuid

import numpy as np
import pandas as pd
from django.db import models
from django.utils.safestring import mark_safe
from tinymce.models import HTMLField

from AdminUtils import get_standard_display_list
from services.DataFrameRender.RenderDfFromModel import create_df_from_model, create_group_button, ButtonData, \
    renamed_dict
import humanize

_t = humanize.activate("ru_RU")


class EmailType(Enum):
    IN = "Входящие"
    OUT = "Исходящие"

    @classmethod
    def choices(cls):
        return [(i.name, i.value) for i in cls]


class Task(models.Model):
    FILTERED_COLUMNS = {
        'id': 'id',
        'project_site__name': "Площадка",
        'sub_project__name': "Проект",
        'building_number__name__name': "Здание",
        'design_chapter__short_name': "Раздел",
        'name': "Описание Задачи",
        'contractor__name': "Ответсвенный",
        'status': "Статус",
        'price': "Цена",
        'due_date': "Окончание"
    }

    owner = models.ForeignKey('auth.User', on_delete=models.CASCADE,
                              related_name='tasks', verbose_name='Владелец')
    # parent = models.ForeignKey('self', on_delete=models.SET_NULL,
    #                            related_name='children_task', verbose_name='Родительская задача', null=True,
    #                            blank=True)
    project_site = models.ForeignKey('StaticData.ProjectSite', verbose_name='Проект',
                                     null=False,
                                     on_delete=models.CASCADE
                                     )
    sub_project = models.ForeignKey('StaticData.SubProject', verbose_name='Подпроект',
                                    null=False,
                                    blank=False,
                                    on_delete=models.DO_NOTHING,
                                    )
    building_number = models.ForeignKey('StaticData.BuildingNumber', verbose_name='Здание', null=True, blank=True,
                                        on_delete=models.CASCADE)
    name = models.CharField(max_length=150, null=False, verbose_name='Наименование Задачи')
    description = HTMLField(verbose_name='Описание', null=True, blank=True)
    design_chapter = models.ForeignKey('StaticData.DesignChapter', verbose_name='Раздел', null=True, blank=True,
                                       on_delete=models.CASCADE
                                       )
    contractor = models.ForeignKey('ProjectContract.Contractor', verbose_name='Ответсвенный', null=True, blank=True,
                                   on_delete=models.CASCADE
                                   )
    status = models.ForeignKey('StaticData.Status', verbose_name='Статус', on_delete=models.DO_NOTHING, default=1,
                               null=True, blank=True)
    category = models.ForeignKey('StaticData.Category', on_delete=models.SET_NULL, verbose_name='Категория',
                                 null=True, blank=True, default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="цена", null=True, blank=True)
    contract = models.ForeignKey('ProjectContract.Contract', on_delete=models.SET_NULL, verbose_name='Договор',
                                 null=True, blank=True)
    due_date = models.DateField(verbose_name="завершение", null=True, blank=True, )
    creation_stamp = models.DateTimeField(auto_now_add=True, verbose_name="дата создания")
    update_stamp = models.DateTimeField(auto_now=True, verbose_name="дата изменения")

    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'
        ordering = ["pk"]

    def __str__(self):
        return self.name

    @property
    def subtask_sum(self):
        qs = SubTask.objects. \
            select_related('parent'). \
            filter(parent__id=self.id). \
            values('price')
        new_price = sum([val.get('price') for val in qs if val.get('price')])
        return new_price

    subtask_sum.fget.short_description = 'Стоим.подзадачи'

    @staticmethod
    def create_pivot_table(qs, _replaced_list: list[str], columns_name: str = 'contract'):
        pivot_table = create_df_from_model(Task, qs)
        pivot_table = pivot_table[pivot_table['price'] > 0]
        for col_name in _replaced_list:
            pivot_table[col_name] = pivot_table[col_name].apply(
                lambda x: x.name if x else None
            )
        pivot_table = pivot_table.pivot_table(
            values='price',
            index=['contractor'],
            columns=columns_name,
            aggfunc='sum',
            margins=True,
            margins_name="ИТОГО"
        )
        _renamed_dict = renamed_dict(Task)
        pivot_table.index.name = _renamed_dict.get('contractor')
        pivot_table.columns.name = ""
        pivot_table = pivot_table.map(lambda x: humanize.intcomma(x).replace(',', ' '))
        pivot_table = pivot_table.to_html(classes="table table-striped table-bordered",
                                          table_id='TaskTable',
                                          index=True,
                                          show_dimensions=False,
                                          render_links=True,
                                          justify='center',
                                          escape=False,
                                          na_rep='-',

                                          )
        return pivot_table

    @staticmethod
    def get_df_render_from_qs() -> pd.DataFrame:
        qs = Task.objects.all().order_by('project_site')
        df_initial = create_df_from_model(Task, qs)
        button_data_copy = ButtonData('TaskCloneView', "pk", name='📄')
        button_data_delete = ButtonData('TaskDeleteView', "pk", cls='danger', name='X')
        button_data_update = ButtonData('TaskUpdateView', "pk")
        # переопределяем название задачи - добавляем ссылку на update
        df_initial['name'] = df_initial.apply(lambda x: button_data_update.create_text_link(x['id'], x['name']), axis=1)
        button_copy = df_initial.apply(lambda x: button_data_copy.button_link(x['id']), axis=1)
        button_delete = df_initial.apply(lambda x: button_data_delete.button_link(x['id']), axis=1)
        df_initial['действия'] = create_group_button([button_copy, button_delete])
        return df_initial


class SubTask(models.Model):
    name = models.CharField(max_length=256, null=True, blank=True, verbose_name='Подзадача')
    parent = models.ForeignKey('ProjectTDL.Task', on_delete=models.CASCADE, verbose_name='Наим. Задачи')
    description = models.TextField(null=True, blank=True, verbose_name='Описание')
    price = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="цена", null=True, blank=True)
    creation_stamp = models.DateTimeField(auto_now_add=True, verbose_name="дата создания")
    update_stamp = models.DateTimeField(auto_now=True, verbose_name="дата изменения")
    due_date = models.DateField(verbose_name="дата завершения", null=True, blank=True)

    def __str__(self):
        return f"Заметка {self.parent.name}"

    class Meta:
        verbose_name = 'Подзадача'
        verbose_name_plural = 'Подзадачи'


class Email(models.Model):
    project_site = models.ForeignKey('StaticData.ProjectSite', verbose_name='Проект',
                                     null=False,
                                     on_delete=models.CASCADE
                                     )
    contractor = models.ForeignKey('ProjectContract.Contractor', verbose_name='Ответсвенный', null=True, blank=True,
                                   on_delete=models.CASCADE
                                   )
    email_type = models.CharField(max_length=10, choices=EmailType.choices(),
                                  default=(EmailType.IN.name, EmailType.IN.value),
                                  verbose_name='Тип Сообщения')
    name = models.CharField(max_length=100, null=True, blank=True, verbose_name='Наименование')
    parent = models.ForeignKey('ProjectTDL.Task', on_delete=models.CASCADE, verbose_name='Род. Задача', null=True,
                               blank=True)
    link = models.CharField(max_length=300, null=True, blank=True, verbose_name='link')
    subject = models.CharField(max_length=300, null=True, blank=True, verbose_name='Тема письма')
    body = models.TextField(null=True, blank=True, verbose_name='Тело письма')
    sender = models.CharField(max_length=300, null=True, blank=True, verbose_name='Отправитель')
    creation_stamp = models.DateTimeField(auto_now_add=True, verbose_name="дата создания")
    update_stamp = models.DateTimeField(auto_now=True, verbose_name="дата изменения")

    @property
    def create_admin_link(self):
        return mark_safe(
            f'<a href="file:///{self.link}">{self.link}</a>'
        )

    create_admin_link.fget.short_description = 'e-mail Данные'

    def __str__(self):
        return f"Ссылка {self.name}"

    class Meta:
        verbose_name = 'E-mail'
        verbose_name_plural = 'E-mail'
