import os
from django.apps import AppConfig


class ProjecttdlConfig(AppConfig):
	default_auto_field = 'django.db.models.BigAutoField'
	name = 'ProjectTDL'
	verbose_name = 'Проекты СИМРУС'

	def ready(self):
		if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('DJANGO_AUTORELOAD'):
			from . import scheduled
			scheduled.start_task()
