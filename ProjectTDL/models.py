from django.db import models
from django.db.models import F, Q, When, Sum
from django.utils.timezone import now


class Task(models.Model):
    project_site = models.ForeignKey('StaticData.ProjectSite', verbose_name='Проект',
                                     null=False,
                                     on_delete=models.CASCADE, default=1
                                     )
    building_number = models.ForeignKey('StaticData.BuildingNumber', verbose_name='Здание', null=True, blank=True,
                                        on_delete=models.CASCADE, default=1)
    name = models.CharField(max_length=150, null=False, verbose_name='Наим. Задачи')
    description = models.TextField(verbose_name='Описание', null=True, blank=True)
    design_chapter = models.ForeignKey('StaticData.DesignChapter', verbose_name='Раздел', null=True, blank=True,
                                       on_delete=models.CASCADE, default=1
                                       )
    contractor = models.ForeignKey('ProjectContract.Contractor', verbose_name='Ответсвенный', null=True, blank=True,
                                   on_delete=models.CASCADE, default=1
                                   )
    # parent = models.ForeignKey('self', on_delete=models.SET_NULL,
    #                            related_name='children_task', verbose_name='Родительская задача', null=True,
    #                            blank=True)
    status = models.ForeignKey('StaticData.Status', verbose_name='Статус', on_delete=models.DO_NOTHING, default=1)
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
        qs = Notes.objects. \
            select_related('parent'). \
            filter(parent__id=self.id). \
            values('price')
        new_price = sum([val.get('price') for val in qs if val.get('price')])
        return new_price

    subtask_sum.fget.short_description = 'Стоим.подзадачи'


class Notes(models.Model):
    name = models.CharField(max_length=100, null=True, blank=True, verbose_name='Заметки')
    parent = models.ForeignKey('ProjectTDL.Task', on_delete=models.CASCADE, verbose_name='Наим. Задачи')
    description = models.TextField(null=True, blank=True, verbose_name='Описание')
    price = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="цена", null=True, blank=True)
    creation_stamp = models.DateTimeField(auto_now_add=True, verbose_name="дата создания")
    update_stamp = models.DateTimeField(auto_now=True, verbose_name="дата изменения")
    due_date = models.DateField(verbose_name="дата завершения", null=True, blank=True)

    def __str__(self):
        return f"Заметка {self.parent.name}"

    class Meta:
        verbose_name = 'Заметка'
        verbose_name_plural = 'Заметки'



