import os
from django.db import models
from django.utils.safestring import mark_safe
from enum import Enum
from urllib.parse import quote

class EmailType(Enum):
    IN = "Входящие"
    OUT = "Исходящие"

    @classmethod
    def choices(cls):
        return [(i.name, i.value) for i in cls]


class InfoChoices(models.TextChoices):
    APPROVED = 'APPROVED', "Согласовано"
    TASK = 'TASK', "Задача"
    FINANCIAL = 'FINANCIAL', "Финансы"


class Email(models.Model):
    FOLDER_CHOICES = [
        ('inbox', 'Входящие'),
        ('sent', 'Отправленные'),
        ('drafts', 'Черновики'),
        ('archive', 'Архив'),
        ('trash', 'Корзина'),
    ]

    uid = models.CharField(max_length=200, null=True, blank=True, verbose_name='uid')
    project_site = models.ForeignKey(
        'StaticData.ProjectSite',
        verbose_name='Проект',
        null=True, blank=True,
        on_delete=models.CASCADE
    )
    building_type = models.ForeignKey(
        'StaticData.BuildingType',
        verbose_name='Здание',
        null=True, blank=True,
        on_delete=models.CASCADE
    )
    category = models.ForeignKey(
        'StaticData.Category',
        on_delete=models.SET_NULL,
        verbose_name='Категория',
        null=True, blank=True,
        default=1
    )
    contractor = models.ForeignKey(
        'ProjectContract.Contractor',
        verbose_name='Подрядчик',
        null=True, blank=True,
        on_delete=models.CASCADE
    )
    email_type = models.CharField(
        max_length=10,
        choices=EmailType.choices(),
        default=(EmailType.IN.name, EmailType.IN.value),
        verbose_name='Тип Сообщения'
    )
    name = models.CharField(max_length=100, null=True, blank=True, verbose_name='Наименование')
    info = models.CharField(
        max_length=20,
        choices=InfoChoices.choices,
        default=InfoChoices.TASK,
        verbose_name="Тип информации",
        null=True, blank=True,
    )
    parent = models.ForeignKey(
        'ProjectTDL.Task',
        on_delete=models.CASCADE,
        verbose_name='Род. Задача',
        null=True, blank=True
    )
    link = models.CharField(max_length=300, null=True, blank=True, verbose_name='Ссылка')
    subject = models.CharField(max_length=300, null=True, blank=True, verbose_name='Тема письма')
    sender = models.CharField(max_length=300, null=True, blank=True, verbose_name='Отправитель')
    receiver = models.CharField(max_length=300, null=True, blank=True, verbose_name='Получатель')
    email_stamp = models.DateTimeField(null=True, blank=True, verbose_name="дата письма")
    creation_stamp = models.DateTimeField(auto_now_add=True, null=True, blank=True, verbose_name="дата создания")
    update_stamp = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name="дата изменения")

    # Новые поля
    is_read = models.BooleanField(default=False, verbose_name='Прочитано')
    is_important = models.BooleanField(default=False, verbose_name='Важное')
    folder = models.CharField(
        max_length=20,
        choices=FOLDER_CHOICES,
        default='inbox',
        verbose_name='Папка'
    )
    tasks = models.ManyToManyField(
        'ProjectTDL.Task',
        blank=True,
        related_name='emails',
        verbose_name='Задачи'
    )

    @property
    def create_admin_link(self):
        return mark_safe(f'<a href="file:///{self.link}">Ссылка</a>')

    create_admin_link.fget.short_description = 'e-mail Данные'

    def get_html_file_path(self):
        """Возвращает полный путь к HTML-файлу письма."""
        if not self.link:
            return None
        # Имя HTML-файла, используемое в парсере
        return os.path.join(self.link, 'custom_table_view.html')

    def __str__(self):
        return f"Ссылка {self.name}"

    class Meta:
        verbose_name = 'E-mail'
        verbose_name_plural = 'E-mail'
        ordering = ['-email_stamp']



class Attachment(models.Model):
    email = models.ForeignKey(
        Email,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Письмо'
    )
    file_path = models.CharField(max_length=500, verbose_name='Путь к файлу')
    filename = models.CharField(max_length=255, verbose_name='Имя файла')
    size = models.IntegerField(verbose_name='Размер (байт)')
    content_type = models.CharField(max_length=100, blank=True, verbose_name='Тип содержимого')
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата загрузки')

    @property
    def file_path_js(self):
        """Возвращает путь, экранированный для использования в JavaScript."""
        return self.file_path.replace('\\', '\\\\').replace("'", "\\'")

    @property
    def file_url(self):
        """Возвращает file:// URL (может не работать в браузере)."""
        path = self.file_path.replace('\\', '/')
        encoded = quote(path, safe=':/')
        return f'file://{encoded}'

    @property
    def folder_path(self):
        """Возвращает путь к папке, содержащей файл."""
        return os.path.dirname(self.file_path)

    @property
    def folder_url(self):
        """Возвращает file:// URL для папки (если разрешено браузером)."""
        path = self.folder_path.replace('\\', '/')
        encoded = quote(path, safe=':/')
        return f'file://{encoded}'

    def __str__(self):
        return self.filename

    class Meta:
        verbose_name = 'Вложение'
        verbose_name_plural = 'Вложения'