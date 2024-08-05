from datetime import datetime
from django.contrib import admin

from AdminUtils import duplicate_event, get_standard_display_list, get_filtered_registered_models
from ProjectTDL.Tables import StaticFilterSettings
from ProjectTDL.forms import EmailForm
from ProjectTDL.models import *
from ProjectContract.models import *
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field

from ProjectTDL.ЕmailParser.EmailFunctions import clean
from StaticData.models import DesignChapter

from django.contrib import messages
import os, shutil
import win32clipboard  # pip install pywin32
from html.parser import HTMLParser
from services.DataFrameRender.RenderDfFromModel import create_pivot_table
from mptt.admin import MPTTModelAdmin
from mptt.admin import DraggableMPTTAdmin


def html_convert(data):
    class HTMLFilter(HTMLParser):
        text = ""

        def handle_data(self, data):
            self.text += data

    if data:
        f = HTMLFilter()
        f.feed(data)
        return f.text
    else:
        return ""


def copy_to_clipboard(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()


def copytree(src, dst, symlinks=False, ignore=None):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, symlinks, ignore)
        else:
            shutil.copy2(s, d)


class DesignChapterResource(resources.ModelResource):
    class Meta:
        model = DesignChapter
        fields = ['id', 'name', 'short_name']


class TaskResource(resources.ModelResource):
    id = Field(attribute='id')
    project_site__name = Field(attribute='project_site__name', column_name='project site')
    sub_project__name = Field(attribute='sub_project__name', column_name='sub project site')
    building_number__name__name = Field(attribute='building_number__name__name', column_name='building')
    building_number__building_number = Field(attribute='building_number__building_number')
    design_chapter__short_name = Field(attribute='design_chapter__short_name', column_name='design chapter')
    design_chapter__full_name = Field(attribute='design_chapter__name', column_name='design chapter')
    name = Field(attribute='name')
    description = Field(attribute='description')
    status__name = Field(attribute='status__name')
    due_date = Field(attribute='due_date')
    price = Field(attribute='price')

    class Meta:
        model = Task
        fields = ('id', 'project_site__name',
                  'sub_project__name',
                  'building_number__name__name',
                  'building_number__building_number',
                  'design_chapter__short_name', 'name', 'description',
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


excluding_list = [Task, Contract, DesignChapter, Email, ContractPayments, PaymentCalendar, ConcretePaymentCalendar]


@admin.register(*get_filtered_registered_models('ProjectContract', excluding_list))
@admin.register(*get_filtered_registered_models('StaticData', excluding_list))
@admin.register(*get_filtered_registered_models('ProjectTDL', excluding_list))
class UniversalAdmin(admin.ModelAdmin):
    actions = [duplicate_event]
    list_display_links = ('id', 'name')
    list_per_page = 20

    def get_list_display(self, request):
        return get_standard_display_list(self.model, excluding_list=['creation_stamp', 'update_stamp', 'link', 'body'])


@admin.register(ContractPayments)
class ContractPaymentsAdmin(admin.ModelAdmin):
    _all_list = ['contract', 'name', 'parent', 'percent', 'price', 'start_date', 'due_date', 'duration']
    list_display = ['id', 'made_payment', 'contractor_name'] + _all_list
    list_filter = ['contract', 'made_payment']
    search_fields = ['contract__name', 'name']
    list_editable = _all_list


@admin.register(Task)
class TaskAdmin(ImportExportModelAdmin):
    excluding_list = ['description', 'parent', 'owner', ]
    additional_list = []
    actions = [duplicate_event, 'update_data', 'html_replace']
    list_display_links = ('id', 'name',)
    list_display = get_standard_display_list(Task, excluding_list=excluding_list, additional_list=additional_list)
    list_editable = ('status', 'price', 'due_date',)  # удалил 'category', 'contractor','contract',
    list_filter = ['project_site__name', 'sub_project', 'building_number', 'status', 'category', 'contractor',
                   'contract', ]
    search_fields = ['name', 'project_site__name', 'sub_project__name', 'contractor__name']
    inlines = [TaskInline, EmailInline]
    resource_classes = [TaskResource]
    list_per_page = 20
    actions_on_bottom = True
    list_footer = True
    change_list_template = 'jazzmin/admin/change_list.html'

    @admin.display(description=" Раздел наименование", ordering='design_chapter')
    def chapter_full_name(self, obj: Task):
        return obj.design_chapter.name

    @admin.action(description='Заменить HTML текст')
    def html_replace(modeladmin, request, queryset):
        for object in queryset:
            try:
                object.description = html_convert(object.description)
                object.save()
                messages.success(request, f'данные записи {object.id} обновлены')
            except Exception as e:
                messages.error(request, f'данные записи {object.id} не обновлены {e}')

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(
            request,
            extra_context=extra_context,
        )
        try:
            qs = response.context_data['cl'].queryset
        except (AttributeError, KeyError):
            return response
        _pivot_ui = None
        pivot_table_list = []
        for name, _column in zip(StaticFilterSettings.pivot_columns_names,
                                 StaticFilterSettings.pivot_columns_values):
            pivot_table1 = {"name": name,
                            'table': create_pivot_table(Task, qs, StaticFilterSettings.replaced_list, _column)}
            pivot_table_list.append(pivot_table1)
        response.context_data['pivot_table_list'] = pivot_table_list
        return response

    class Media(object):
        js = ('admin/js/admin.js',)


# css = {"all": ("admin/admin_css.css",)}


@admin.register(DesignChapter)
class ContractAdmin(ImportExportModelAdmin):
    actions = [duplicate_event]
    resource_classes = [DesignChapterResource]
    list_display = get_standard_display_list(DesignChapter)


@admin.register(Email)
class EmailAdmin(ImportExportModelAdmin):
    list_display = ['id', 'email_type', 'project_site', 'building_type', 'category', 'contractor', 'name',
                    'subject', 'sender', 'email_stamp', 'create_admin_link']
    # list_editable = ['project_site', 'contractor']
    list_filter = ['email_type', 'project_site', 'contractor', 'sender']
    search_fields = ['name', 'subject', 'sender']
    list_display_links = ['id', 'name', 'subject']
    change_list_template = 'jazzmin/admin/change_list.html'
    actions = ("copy_e_mail",)

    @admin.action(description='Скопировать E-mail')
    def copy_e_mail(modeladmin, request, queryset):
        for obj in queryset:
            try:
                email_type = getattr(EmailType, obj.email_type).value
                year = str(datetime.now().year)
                today = datetime.today().strftime('%Y_%m_%d')
                folder_name = obj.name if obj.name else clean(obj.subject)
                _directory = os.path.join(
                    'C:\\', 'Bitrix 24', 'Переписка', obj.project_site.name,
                    obj.contractor.name, email_type, year, f'{today}_{folder_name}\\'
                )
                os.makedirs(_directory, exist_ok=True)
                copytree(obj.link, _directory)
                if os.path.isdir(_directory):
                    copy_to_clipboard(_directory)
                messages.success(request, f"файлы скопированы в папку {_directory}")
            except Exception as e:
                messages.error(request, f"ошибки при копировании {e}")

# form = EmailForm
