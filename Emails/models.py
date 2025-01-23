from enum import Enum

from django.db import models
from django.utils.safestring import mark_safe
from tinymce.models import HTMLField


class EmailType(Enum):
	IN = "Входящие"
	OUT = "Исходящие"

	@classmethod
	def choices(cls):
		return [(i.name, i.value) for i in cls]


class Email(models.Model):
	uid = models.CharField(max_length=200, null=True, blank=True, verbose_name='uid')
	project_site = models.ForeignKey('StaticData.ProjectSite', verbose_name='Проект',
	                                 null=True, blank=True,
	                                 on_delete=models.CASCADE
	                                 )
	building_type = models.ForeignKey('StaticData.BuildingType', verbose_name='Здание', null=True, blank=True,
	                                  on_delete=models.CASCADE)
	category = models.ForeignKey('StaticData.Category', on_delete=models.SET_NULL, verbose_name='Категория',
	                             null=True, blank=True, default=1)
	contractor = models.ForeignKey('ProjectContract.Contractor', verbose_name='Подрядчик', null=True, blank=True,
	                               on_delete=models.CASCADE
	                               )
	email_type = models.CharField(max_length=10, choices=EmailType.choices(),
	                              default=(EmailType.IN.name, EmailType.IN.value),
	                              verbose_name='Тип Сообщения')
	name = models.CharField(max_length=100, null=True, blank=True, verbose_name='Наименование')
	parent = models.ForeignKey('ProjectTDL.Task', on_delete=models.CASCADE, verbose_name='Род. Задача', null=True,
	                           blank=True)
	link = models.CharField(max_length=300, null=True, blank=True, verbose_name='Ссылка')
	subject = models.CharField(max_length=300, null=True, blank=True, verbose_name='Тема письма')
	body = HTMLField(null=True, blank=True, verbose_name='Тело письма')
	sender = models.CharField(max_length=300, null=True, blank=True, verbose_name='Отправитель')
	receiver = models.CharField(max_length=300, null=True, blank=True, verbose_name='Получатель')
	email_stamp = models.DateTimeField(null=True, blank=True, verbose_name="дата письма")
	creation_stamp = models.DateTimeField(auto_now_add=True, null=True, blank=True, verbose_name="дата создания")
	update_stamp = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name="дата изменения")

	@property
	def create_admin_link(self):
		return mark_safe(
			f'<a href="file:///{self.link}">Ссылка</a>'
		)

	create_admin_link.fget.short_description = 'e-mail Данные'

	def __str__(self):
		return f"Ссылка {self.name}"

	class Meta:
		verbose_name = 'E-mail'
		verbose_name_plural = 'E-mail'
		ordering = ['-email_stamp']

