from django.db import models


class ProjectSite(models.Model):
	name = models.CharField(max_length=100, null=False, verbose_name='Наименование Проекта')

	class Meta:
		verbose_name = 'Проект'
		verbose_name_plural = 'Проекты'

	def __str__(self):
		return self.name


class SubProject(models.Model):
	name = models.CharField(max_length=100, null=False, verbose_name='Подпроект')

	class Meta:
		verbose_name = 'Подпроект'
		verbose_name_plural = 'Подпроекты'

	def __str__(self):
		return self.name


class BuildingType(models.Model):
	name = models.CharField(max_length=100, null=False, verbose_name='Наименование Здания')

	class Meta:
		verbose_name = 'Здание Тип'
		verbose_name_plural = 'Здания Тип'

	def __str__(self):
		return self.name


class BuildingNumber(models.Model):
	name = models.ForeignKey('StaticData.BuildingType', verbose_name='Тип здания', null=True, blank=True,
	                         on_delete=models.SET_NULL)
	building_number = models.CharField(max_length=20, null=True, verbose_name='Номер Здания')

	class Meta:
		verbose_name = 'Здание Номер'
		verbose_name_plural = 'Здания Номер'

	def __str__(self):
		return f'{self.name.name} {self.building_number}'


class DesignChapter(models.Model):
	name = models.CharField(max_length=150, null=False, verbose_name='Наим. Раздела')
	short_name = models.CharField(max_length=150, null=False, verbose_name='Шифр раздела')

	class Meta:
		verbose_name = 'Раздел Документации'
		verbose_name_plural = 'Разделы Документации'

	def __str__(self):
		return self.short_name


class Status(models.Model):
	name = models.CharField(max_length=150, null=False, verbose_name='Статус')

	class Meta:
		verbose_name = 'Статус задачи'
		verbose_name_plural = 'Статус задач'

	def __str__(self):
		return self.name
