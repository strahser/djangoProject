# models.py - ОКОНЧАТЕЛЬНАЯ ВЕРСИЯ (упрощенная)
import humanize
from django.db import models
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from tinymce.models import HTMLField

_t = humanize.activate("ru_RU")

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

# ОПРЕДЕЛЕНИЕ МОДЕЛЕЙ БЕЗ ИМПОРТОВ ИЗ ДРУГИХ МОДУЛЕЙ ПРОЕКТА
class Task(models.Model):
    owner = models.ForeignKey('auth.User', on_delete=models.CASCADE,
                              related_name='tasks', verbose_name='Владелец')
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

    def __str__(self):
        return self.name

    @property
    def subtask_sum(self):
        from .models import SubTask  # Локальный импорт для избежания цикла
        qs = SubTask.objects. \
            select_related('parent'). \
            filter(parent__id=self.id). \
            values('price')
        new_price = sum([val.get('price') for val in qs if val.get('price')])
        return new_price

    subtask_sum.fget.short_description = 'Стоим.подзадачи'


class TaskDueDateHistory(models.Model):
    """Модель для хранения истории изменений сроков выполнения задачи"""
    task = models.ForeignKey(Task, on_delete=models.CASCADE, verbose_name="Задача", related_name='due_date_history')
    old_due_date = models.DateField(verbose_name="Предыдущая дата", null=True, blank=True)
    new_due_date = models.DateField(verbose_name="Новая дата", null=True, blank=True)
    change_date = models.DateTimeField(auto_now_add=True, verbose_name="Дата изменения")
    changed_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, verbose_name="Кто изменил", null=True, blank=True)

    class Meta:
        verbose_name = 'История изменения срока задачи'
        verbose_name_plural = 'История изменений сроков задач'
        ordering = ['-change_date']

    def __str__(self):
        return f"Изменение сроков для {self.task.name}"


@receiver(pre_save, sender=Task)
def track_due_date_change(sender, instance, **kwargs):
    """Сигнал для отслеживания изменений даты выполнения задачи"""
    if instance.pk:
        try:
            old_task = Task.objects.get(pk=instance.pk)
            if old_task.due_date != instance.due_date:
                # Сохраняем старую дату в экземпляре для использования в post_save
                instance._old_due_date = old_task.due_date
        except Task.DoesNotExist:
            pass


@receiver(post_save, sender=Task)
def create_due_date_history(sender, instance, created, **kwargs):
    """Сигнал для создания записи в истории при изменении даты выполнения"""
    if not created and hasattr(instance, '_old_due_date'):
        # Получаем текущего пользователя
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # В реальном приложении нужно получить пользователя из request
        user = User.objects.first()

        TaskDueDateHistory.objects.create(
            task=instance,
            old_due_date=instance._old_due_date,
            new_due_date=instance.due_date,
            changed_by=user
        )


class SubTask(models.Model):
    name = models.CharField(max_length=256, null=True, blank=True, verbose_name='Подзадача')
    parent = models.ForeignKey('ProjectTDL.Task', on_delete=models.CASCADE, verbose_name='Род. Задача')
    description = HTMLField(null=True, blank=True, verbose_name='Описание')
    price = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="цена", null=True, blank=True)
    creation_stamp = models.DateTimeField(auto_now_add=True, verbose_name="дата создания")
    update_stamp = models.DateTimeField(auto_now=True, verbose_name="дата изменения")
    due_date = models.DateField(verbose_name="дата завершения", null=True, blank=True)

    def __str__(self):
        return f"Заметка {self.parent.name}"

    class Meta:
        verbose_name = 'Подзадача'
        verbose_name_plural = 'Подзадачи'