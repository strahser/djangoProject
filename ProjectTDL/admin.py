import django_filters
from django.contrib import admin
from django import forms
from django.contrib.admin import ListFilter
from django.urls import reverse
from import_export.forms import ExportForm
from more_admin_filters import MultiSelectDropdownFilter, MultiSelectFilter, DropdownFilter, ChoicesDropdownFilter, \
    MultiSelectRelatedFilter
from import_export.admin import ExportActionModelAdmin
from AdminUtils import duplicate_event, get_standard_display_list, get_filtered_registered_models
from ProjectTDL.forms import EmailForm
from ProjectTDL.models import *
from ProjectContract.models import *
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field
from StaticData.models import DesignChapter, Status


class DesignChapterResource(resources.ModelResource):
    class Meta:
        model = DesignChapter
        fields = ['id', 'name', 'short_name']


class TaskResource(resources.ModelResource):
    id = Field(attribute='id', column_name='#')
    project_site__name = Field(attribute='project_site__name', column_name='Проект')
    sub_project__name = Field(attribute='sub_project__name', column_name='Подпроект')
    building_number__name__name = Field(attribute='building_number__name__name', column_name='Здание')
    building_number__building_number = Field(attribute='building_number__building_number', column_name='Номер')
    design_chapter__short_name = Field(attribute='design_chapter__short_name', column_name='РД')
    name = Field(attribute='name', column_name='Название задачи')
    description = Field(attribute='description', column_name='Описание')
    status__name = Field(attribute='status__name', column_name='Статус')
    due_date = Field(attribute='due_date', column_name='Дата окончания')
    subtask_sum = Field(attribute='subtask_sum', column_name='Сумма подзадач')

    class Meta:
        model = Task
        fields = ('id', 'project_site__name',
                  'sub_project__name',
                  'building_number__name__name',
                  'building_number__building_number', 'design_chapter__short_name', 'name', 'description',
                  'status__name', 'due_date'
                  )
        export_order = ('id', 'project_site__name')


class TaskInline(admin.TabularInline):
    model = SubTask
    extra = 0
    fields = get_standard_display_list(SubTask, additional_list=['creation_stamp'])
    readonly_fields = ('creation_stamp',)


class EmailInline(admin.TabularInline):
    model = Email
    extra = 0
    fields = ['project_site', 'contractor', 'email_type', 'name', 'parent']
    readonly_fields = ['create_admin_link']
    form = EmailForm


class ContractPaymentsInline(admin.TabularInline):
    model = ContractPayments
    extra = 0


excluding_list = [Task, Contract, DesignChapter]


@admin.register(*get_filtered_registered_models('ProjectContract', excluding_list))
@admin.register(*get_filtered_registered_models('StaticData', excluding_list))
@admin.register(*get_filtered_registered_models('ProjectTDL', excluding_list))
class UniversalAdmin(admin.ModelAdmin):
    actions = [duplicate_event]
    list_display_links = ('id', 'name')
    list_per_page = 10

    def get_list_display(self, request):
        return get_standard_display_list(self.model, excluding_list=['creation_stamp', 'update_stamp', 'link', 'body'])


@admin.register(Task)
class TaskAdmin(ImportExportModelAdmin):
    var = ['lft', 'rght', 'tree_id', 'level']
    actions = [duplicate_event]
    list_display_links = ('id', 'name')
    list_display = get_standard_display_list(Task, excluding_list=['description', 'contract', 'parent'])
    list_editable = ('status', 'price', 'due_date')
    list_filter = ['project_site__name', 'sub_project', 'building_number', 'status', 'contractor']
    advanced_filter_fields = ('project_site__name', 'sub_project',)
    inlines = [TaskInline, EmailInline]
    resource_classes = [TaskResource]
    list_per_page = 10
    actions_on_bottom = True

    class Media(object):
        js = ('admin/js/admin.js',)


@admin.register(Contract)
class ContractAdmin(UniversalAdmin):
    actions = [duplicate_event]
    inlines = (ContractPaymentsInline,)


@admin.register(DesignChapter)
class ContractAdmin(ImportExportModelAdmin):
    actions = [duplicate_event]
    resource_classes = [DesignChapterResource]
    list_display = get_standard_display_list(DesignChapter)
