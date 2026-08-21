from django.conf import settings
from django.db import models
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from tinymce.models import HTMLField


class TaskDueDateHistory(models.Model):
    task_node = models.ForeignKey('TaskNode', on_delete=models.CASCADE, verbose_name="Задача",
                                  related_name='due_date_history', null=True, blank=True)
    old_due_date = models.DateField(verbose_name="Предыдущая дата", null=True, blank=True)
    new_due_date = models.DateField(verbose_name="Новая дата", null=True, blank=True)
    change_date = models.DateTimeField(auto_now_add=True, verbose_name="Дата изменения")
    changed_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, verbose_name="Кто изменил", null=True,
                                   blank=True)

    class Meta:
        verbose_name = 'История изменения срока задачи'
        verbose_name_plural = 'История изменений сроков задач'
        ordering = ['-change_date']

    def __str__(self):
        return f"Изменение сроков для {self.task_node.name if self.task_node_id else '—'}"


@receiver(pre_save, sender='ProjectTDL.TaskNode')
def track_due_date_change_node(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_node = instance.__class__.objects.get(pk=instance.pk)
            if old_node.due_date != instance.due_date:
                instance._old_due_date = old_node.due_date
        except instance.__class__.DoesNotExist:
            pass


@receiver(post_save, sender='ProjectTDL.TaskNode')
def create_due_date_history_node(sender, instance, created, **kwargs):
    if not created and hasattr(instance, '_old_due_date'):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.first()
        TaskDueDateHistory.objects.create(
            task_node=instance,
            old_due_date=instance._old_due_date,
            new_due_date=instance.due_date,
            changed_by=user
        )


from mptt.models import MPTTModel, TreeForeignKey

class TaskNode(MPTTModel):
    """Единая рекурсивная модель: задача и подзадача в одной таблице."""
    NODE_TYPES = [('task', 'Задача'), ('subtask', 'Подзадача')]

    owner = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='task_nodes', verbose_name='Владелец')
    parent = TreeForeignKey('self', null=True, blank=True, related_name='children',
                            on_delete=models.CASCADE, verbose_name='Родитель')
    node_type = models.CharField(max_length=10, choices=NODE_TYPES, default='task', verbose_name='Тип')
    project_site = models.ForeignKey('StaticData.ProjectSite', on_delete=models.CASCADE, verbose_name='Проект')
    building_number = models.ForeignKey('StaticData.BuildingNumber', null=True, blank=True, on_delete=models.CASCADE, verbose_name='Здание')
    design_chapter = models.ForeignKey('StaticData.DesignChapter', null=True, blank=True, on_delete=models.CASCADE, verbose_name='Раздел')
    contractor = models.ForeignKey('ProjectContract.Contractor', null=True, blank=True, on_delete=models.CASCADE, verbose_name='Ответственный')
    status = models.ForeignKey('StaticData.Status', on_delete=models.DO_NOTHING, default=1, null=True, blank=True, verbose_name='Статус')
    category = models.ForeignKey('StaticData.Category', on_delete=models.SET_NULL, null=True, blank=True, default=1, verbose_name='Категория')
    contract = models.ForeignKey('ProjectContract.Contract', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Договор')
    name = models.CharField(max_length=150, verbose_name='Наименование')
    description = HTMLField(null=True, blank=True, verbose_name='Описание')
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0, null=True, blank=True, verbose_name='Цена')
    due_date = models.DateField(null=True, blank=True, verbose_name='Завершение')
    creation_stamp = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    update_stamp = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class MPTTMeta:
        order_insertion_by = ['name']

    class Meta:
        verbose_name = 'Задача (дерево)'
        verbose_name_plural = 'Задачи (дерево)'

    def __str__(self):
        return self.name

    @property
    def subtree_price(self):
        from django.db.models import Sum
        agg = self.get_descendants().aggregate(total=Sum('price'))
        return agg['total'] or 0


class ProjectPin(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='Пользователь')
    project_site = models.ForeignKey('StaticData.ProjectSite', on_delete=models.CASCADE, verbose_name='Проект')

    class Meta:
        verbose_name = 'Закреплённый проект'
        verbose_name_plural = 'Закреплённые проекты'
        unique_together = ('user', 'project_site')

    def __str__(self):
        return f'{self.project_site.name} ({self.user.username})'


class UserSettings(models.Model):
    inherit_props = models.BooleanField(default=False, verbose_name='Наследовать свойства от родителя')
    new_task_position = models.CharField(max_length=10, default='bottom', verbose_name='Порядок новых подзадач',
                                         choices=[('top', 'Вверху списка'), ('bottom', 'Внизу списка')])
    default_tree_view = models.BooleanField(default=False, verbose_name='Дерево по умолчанию')
    default_project_site = models.BooleanField(default=False, verbose_name='Заполнять проект из контекста')
    default_category = models.BooleanField(default=False, verbose_name='Заполнять категорию из контекста')
    default_status = models.BooleanField(default=False, verbose_name='Заполнять статус из контекста')
    default_contractor = models.BooleanField(default=False, verbose_name='Заполнять ответственного из контекста')
    default_building = models.BooleanField(default=False, verbose_name='Заполнять здание из контекста')
    column_visibility = models.JSONField(default=dict, verbose_name='Видимость колонок')
    column_widths = models.JSONField(default=dict, verbose_name='Ширины колонок')
    column_order = models.JSONField(default=list, verbose_name='Порядок колонок')
    panel_fields = models.JSONField(default=dict, verbose_name='Поля панели свойств')
    page_length = models.IntegerField(null=True, blank=True, verbose_name='Записей на страницу')
    auto_save = models.BooleanField(default=True, verbose_name='Сохранять состояние фильтров')
    active_project = models.ForeignKey('StaticData.ProjectSite', null=True, blank=True, on_delete=models.SET_NULL,
                                       verbose_name='Активный проект')
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='task_user_settings', verbose_name='Пользователь')

    class Meta:
        verbose_name = 'Настройки пользователя'
        verbose_name_plural = 'Настройки пользователей'

    def __str__(self):
        return f'Настройки {self.user.username}'


class TaskFilterState(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='task_filter_states', verbose_name='Пользователь')
    project_site = models.ForeignKey('StaticData.ProjectSite', on_delete=models.CASCADE, null=True, blank=True,
                                     verbose_name='Проект')
    params = models.JSONField(default=dict, verbose_name='Параметры фильтров')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'Сохранённое состояние фильтров'
        verbose_name_plural = 'Сохранённые состояния фильтров'
        unique_together = ('user', 'project_site')

    def __str__(self):
        return f'Фильтры {self.user.username} · {self.project_site or "все проекты"}'
