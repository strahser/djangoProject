from enum import Enum

from django.db import models
from django.utils.safestring import mark_safe
from tinymce.models import HTMLField
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _


class EmailType(Enum):
    IN = "Входящие"
    OUT = "Исходящие"

    @classmethod
    def choices(cls):
        return [(i.name, i.value) for i in cls]


class Task(models.Model):
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
    name = models.CharField(max_length=150, null=False, verbose_name='Наим. Задачи')
    description = HTMLField(verbose_name='Описание', null=True, blank=True)
    design_chapter = models.ForeignKey('StaticData.DesignChapter', verbose_name='Раздел', null=True, blank=True,
                                       on_delete=models.CASCADE
                                       )
    contractor = models.ForeignKey('ProjectContract.Contractor', verbose_name='Ответсвенный', null=True, blank=True,
                                   on_delete=models.CASCADE
                                   )
    # parent = models.ForeignKey('self', on_delete=models.SET_NULL,
    #                            related_name='children_task', verbose_name='Родительская задача', null=True,
    #                            blank=True)
    status = models.ForeignKey('StaticData.Status', verbose_name='Статус', on_delete=models.DO_NOTHING, default=1,
                               null=True, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="цена", null=True, blank=True)
    contract = models.ForeignKey('ProjectContract.Contract', on_delete=models.SET_NULL, verbose_name='Договор',
                                 null=True, blank=True)
    due_date = models.DateField(verbose_name="дата завершения", null=True, blank=True, )
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
            '<button type="button" class="btn btn-success form-control" data-dismiss="alert" aria-hidden="true" >Данные</button>')

    create_admin_link.fget.short_description = 'e-mail Данные'

    def __str__(self):
        return f"Ссылка {self.name}"

    class Meta:
        verbose_name = 'E-mail'
        verbose_name_plural = 'E-mail'
