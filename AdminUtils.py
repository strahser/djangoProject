from django.apps import apps
from django.db import models
from loguru import logger


def duplicate_event(modeladmin, request, queryset):
    for data in queryset:
        data.id = None
        data.save()


duplicate_event.short_description = "копировать выбранное"
def duplicate_object(obj): # Функция дублирования объекта
    obj.pk = None
    obj.save()


def get_standard_display_list(model, excluding_list: list[str] = None, additional_list: list[str] = None,
                              skip_time_stamps=True):
    time_stamps = ["creation_stamp", 'update_stamp'] if skip_time_stamps else []
    additional_list = additional_list if additional_list else []
    excluding_list = excluding_list if excluding_list else []
    excluding_list = time_stamps + excluding_list
    return [f.name for f in model._meta.fields if f.name not in excluding_list] + additional_list


def get_filtered_registered_models(model_name: str, _excluding_list: list[models] = None):
    _excluding_list = _excluding_list if _excluding_list else []
    project_tdl_models = apps.get_app_config(model_name).get_models()
    return [model for model in project_tdl_models if model not in _excluding_list]
