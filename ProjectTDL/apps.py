from django.apps import AppConfig
from . import scheduled


class ProjecttdlConfig(AppConfig):
	default_auto_field = 'django.db.models.BigAutoField'
	name = 'ProjectTDL'
	verbose_name = 'Проекты СИМРУС'

	def ready(self):
		scheduled.start_task()
