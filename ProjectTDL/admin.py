import logging
from html.parser import HTMLParser

from django.contrib import admin
from django.contrib import messages
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field

from AdminUtils import duplicate_event, get_standard_display_list, get_filtered_registered_models
from Emails.models import Email
from ProjectContract.models import Contract, ContractPayments, PaymentCalendar, ConcretePaymentCalendar
from ProjectTDL.Tables import StaticFilterSettings
from ProjectTDL.models import Task, SubTask
from StaticData.models import DesignChapter
from services.DataFrameRender.RenderDfFromModel import create_pivot_table

logger = logging.getLogger(__name__)


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
    fields = ['name', 'parent', 'subject', 'sender', ]
    readonly_fields = ['name', 'parent', 'subject', 'sender']
    list_display_links = ('id', 'name',)
    show_change_link = True
    show_full_result_count = True
    # form = EmailForm


excluding_list = [Task, Contract, DesignChapter,  ContractPayments, PaymentCalendar, ConcretePaymentCalendar]


@admin.register(*get_filtered_registered_models('ProjectContract', excluding_list))
@admin.register(*get_filtered_registered_models('ProjectTDL', excluding_list))
class UniversalAdmin(admin.ModelAdmin):
    actions = [duplicate_event]
    list_display_links = ('id', 'name')
    list_per_page = 20

    def get_list_display(self, request):
        return get_standard_display_list(self.model, excluding_list=['creation_stamp', 'update_stamp', 'link', 'body'])


@admin.register(Task)
class TaskAdmin(ImportExportModelAdmin):
    excluding_list = ['description', 'parent', 'owner', 'contract', ]
    additional_list = ['add_emails_button']
    actions = [duplicate_event, 'update_data', 'html_replace']
    list_display_links = ('id', 'name',)
    list_display = get_standard_display_list(Task, excluding_list=excluding_list, additional_list=additional_list)
    list_editable = ('status', 'price', 'due_date',)
    list_filter = ['project_site__name', 'sub_project', 'building_number',
                   'status', 'category', 'contractor', 'contract', ]
    search_fields = ['name', 'project_site__name', 'sub_project__name', 'contractor__name']
    inlines = [TaskInline, EmailInline]
    resource_classes = [TaskResource]
    list_per_page = 20
    actions_on_bottom = True
    list_footer = True
    change_list_template = 'jazzmin/admin/change_list.html'

    def add_emails_button(self, obj):
        url = reverse('select_email', args=[obj.pk])
        return format_html(f'<a href="{url}" class="button">✉️</a>')

    add_emails_button.short_description = 'Email'

    def email_list(self, obj):
        emails = obj.email_set.all()
        email_links = []
        for email in emails:
            link = reverse("admin:ProjectTDL_email_change", args=[email.id])
            email_links.append(f'<a href="{link}">{email.subject}</a>')
        return mark_safe(", ".join(email_links))

    email_list.short_description = 'Список Email'

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



