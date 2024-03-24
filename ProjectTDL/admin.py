from django.contrib import admin
from AdminUtils import duplicate_event, get_standard_display_list, get_filtered_registered_models
from ProjectTDL.forms import TaskForm
from ProjectTDL.models import *
from ProjectContract.models import *
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field
from import_export.admin import ExportActionModelAdmin


class TaskResource(resources.ModelResource):
    id = Field(attribute='id', column_name='#')
    project_site__name = Field(attribute='project_site__name', column_name='Проект')
    building_number__name__name = Field(attribute='building_number__name__name', column_name='Здание')
    building_number__name = Field(attribute='building_number__name', column_name='Номер')
    name = Field(attribute='name', column_name='Название задачи')
    description = Field(attribute='description', column_name='Описание')
    design_chapter__short_name = Field(attribute='design_chapter__short_name', column_name='РД')
    status__name = Field(attribute='status__name', column_name='Статус')
    due_date = Field(attribute='due_date', column_name='Дата окончания')

    class Meta:
        model = Task
        fields = ('id', 'project_site__name',
                  'building_number__name__name', 'building_number__name', 'name', 'description',
                  'design_chapter__short_name', 'status__name', 'due_date'
                  )
        export_order = ('id', 'project_site__name')


class NotesInline(admin.TabularInline):
    model = Notes
    extra = 0
    fields = get_standard_display_list(Notes, )
    # form = SubtaskForm


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0


class ContractPaymentsInline(admin.TabularInline):
    model = ContractPayments
    extra = 0


excluding_list = [Task, Contract,Notes]


@admin.register(*get_filtered_registered_models('ProjectContract', excluding_list))
@admin.register(*get_filtered_registered_models('StaticData', excluding_list))
class UniversalAdmin(admin.ModelAdmin):
    actions = [duplicate_event]
    list_display_links = ('id', 'name')
    list_per_page = 10

    def get_list_display(self, request):
        return get_standard_display_list(self.model, excluding_list=['creation_stamp', 'update_stamp'])


@admin.register(Task)
class TaskAdmin(ImportExportModelAdmin):
    var = ['lft', 'rght', 'tree_id', 'level']
    actions = [duplicate_event]
    list_display_links = ('id', 'name')
    list_display = get_standard_display_list(Task, additional_list=['subtask_sum'],
                                             excluding_list=['description', 'contract', 'parent'])
    # form = TaskForm
    search_fields = ['project_site__name']
    list_editable = ('status', 'price',)
    list_filter = ['project_site__name', 'building_number', 'status']
    inlines = [NotesInline, ]
    resource_classes = [TaskResource]


@admin.register(Contract)
class ContractAdmin(UniversalAdmin):
    inlines = (ContractPaymentsInline,)

