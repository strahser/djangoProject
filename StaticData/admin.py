from django.contrib import admin

from AdminUtils import get_standard_display_list, duplicate_event, get_filtered_registered_models
from StaticData.models import DesignChapter

#: Модели StaticData с выделенными админками (DesignChapterAdmin живёт
#: в ProjectTDL/admin). Блок 17: раньше тянули общий список из
#: ProjectTDL.admin — цикл StaticData <-> ProjectTDL держался на порядке
#: импортов; локальный список даёт тот же состав без зависимости.
excluding_list = [DesignChapter]


@admin.register(*get_filtered_registered_models('StaticData', excluding_list))
class UniversalAdmin(admin.ModelAdmin):
    actions = [duplicate_event]
    list_display_links = ('id', )
    list_per_page = 20

    def get_list_display(self, request):
        return get_standard_display_list(self.model, excluding_list=['creation_stamp', 'update_stamp', 'link', 'body'])