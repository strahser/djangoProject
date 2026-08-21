import logging
from urllib.parse import urlencode, parse_qs

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field

from AdminUtils import duplicate_event, get_standard_display_list, get_filtered_registered_models
from Emails.models import Email
from email_ui.models import EmailTaskLink
from ProjectContract.models import Contract, ContractPayments, PaymentCalendar, ConcretePaymentCalendar
from ProjectTDL.Tables import StaticFilterSettings
from mptt.admin import MPTTModelAdmin
from ProjectTDL.models import TaskDueDateHistory, TaskNode
from ProjectTDL.reports import ReportGenerator, html_convert
from StaticData.models import DesignChapter
from services.DataFrameRender.RenderDfFromModel import create_pivot_table

logger = logging.getLogger(__name__)


class DesignChapterResource(resources.ModelResource):
    class Meta:
        model = DesignChapter
        fields = ['id', 'name', 'short_name']


class TaskNodeResource(resources.ModelResource):
    id = Field(attribute='id')
    project_site__name = Field(attribute='project_site__name', column_name='project site')
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
        model = TaskNode
        fields = ('id', 'project_site__name',
                  'building_number__name__name',
                  'building_number__building_number',
                  'design_chapter__short_name', 'name', 'description',
                  'status__name', 'due_date'
                  )
        export_order = ('id', 'project_site__name')


class TaskDueDateHistoryInline(admin.StackedInline):
    model = TaskDueDateHistory
    fk_name = 'task_node'
    extra = 0
    max_num = 0
    can_delete = False
    readonly_fields = ['old_due_date', 'new_due_date', 'change_date', 'changed_by']

    def has_add_permission(self, request, obj=None):
        return False


class TaskInline(admin.StackedInline):
    model = TaskNode
    fk_name = 'parent'
    extra = 1
    fields = ['name', 'description', 'price', 'due_date', 'creation_stamp']
    readonly_fields = ('creation_stamp',)
    verbose_name = 'Подзадача'
    verbose_name_plural = 'Подзадачи'

    def get_queryset(self, request):
        return super().get_queryset(request).filter(node_type='subtask')

    def formfield_for_dbfield(self, db_field, **kwargs):
        field = super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == 'node_type':
            field.initial = 'subtask'
            field.widget = forms.HiddenInput()
        return field


class TaskEmailLinkInline(admin.TabularInline):
    """Inline для связей писем с задачей (EmailTaskLink)."""
    model = EmailTaskLink
    fk_name = 'task_node'
    extra = 0
    fields = ['email_link', 'link_type', 'created_by', 'created_at']
    readonly_fields = ['email_link', 'link_type', 'created_by', 'created_at']

    def email_link(self, obj):
        if obj.email_id:
            url = reverse('admin:Emails_email_change', args=[obj.email_id])
            return format_html('<a href="{}">{}</a>', url, obj.email.subject or str(obj.email_id))
        return '—'
    email_link.short_description = 'Письмо'

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True

    class Media:
        pass


excluding_list = [TaskNode, Contract, DesignChapter, ContractPayments, PaymentCalendar, ConcretePaymentCalendar]


@admin.register(*get_filtered_registered_models('ProjectContract', excluding_list))
@admin.register(*get_filtered_registered_models('ProjectTDL', excluding_list))
class UniversalAdmin(admin.ModelAdmin):
    actions = [duplicate_event]
    list_display_links = ('id', 'name')
    list_per_page = 20

    def get_list_display(self, request):
        return get_standard_display_list(self.model, excluding_list=['creation_stamp', 'update_stamp', 'link', 'body'])


@admin.register(TaskNode)
class TaskNodeAdmin(MPTTModelAdmin, ImportExportModelAdmin):
    excluding_list = ['description', 'parent', 'owner', 'contract', 'lft', 'rght', 'tree_id', 'level', ]
    additional_list = ['creation_stamp', 'add_emails_button', 'add_report_button']
    actions = [duplicate_event, 'html_replace', 'generate_html_report']
    list_display_links = ('id',)
    list_display = get_standard_display_list(TaskNode, excluding_list=excluding_list, additional_list=additional_list)
    list_editable = ('status', 'category', 'price', 'due_date',)
    list_filter = ['project_site__name', 'building_number',
                   'status', 'category', 'contractor', 'contract', 'node_type', ]
    search_fields = ['name', 'project_site__name', 'contractor__name']
    inlines = [TaskInline, TaskEmailLinkInline, TaskDueDateHistoryInline]
    resource_classes = [TaskNodeResource]
    list_per_page = 20
    actions_on_bottom = True
    list_footer = True
    mptt_level_indent = 20
    change_list_template = 'jazzmin/admin/change_list.html'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        email_id = request.POST.get('_email_id') or request.GET.get('_email_id')
        if email_id and not change:
            try:
                from Emails.models import Email
                email = Email.objects.get(pk=email_id)
                EmailTaskLink.objects.create(
                    email=email, task_node=obj,
                    link_type='created_from', created_by=request.user,
                )
            except Exception:
                pass

    def response_add(self, request, obj, post_url_continue=None):
        next_url = request.POST.get('_next')
        if next_url:
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(next_url)
        return super().response_add(request, obj, post_url_continue)

    def render_change_form(self, request, context, *args, **kwargs):
        next_url = request.GET.get('_next')
        email_id = request.GET.get('email_id')
        if next_url:
            context['next_url'] = next_url
        if email_id:
            context['email_id'] = email_id
        return super().render_change_form(request, context, *args, **kwargs)

    def add_emails_button(self, obj):
        url = reverse('select_email', args=[obj.pk])
        return format_html(f'<a href="{url}" class="button">✉️</a>')

    add_emails_button.short_description = 'Email'

    def add_report_button(self, obj):
        url = reverse('generate_custom_report') + f'?task_ids={obj.pk}'
        return format_html(f'<a href="{url}" class="button" target="_blank" title="Сгенерировать отчет">📊</a>')

    add_report_button.short_description = 'Отчет'

    def email_list(self, obj):
        email_ids = EmailTaskLink.objects.filter(task_node=obj).values_list('email_id', flat=True)
        emails = Email.objects.filter(id__in=email_ids)
        email_links = []
        for email in emails:
            link = reverse("admin:Emails_email_change", args=[email.id])
            email_links.append(f'<a href="{link}">{email.subject}</a>')
        return mark_safe(", ".join(email_links))

    email_list.short_description = 'Список Email'

    @admin.action(description='Заменить HTML текст')
    def html_replace(modeladmin, request, queryset):
        for obj in queryset:
            try:
                obj.description = html_convert(obj.description)
                obj.save()
                messages.success(request, f'данные записи {obj.id} обновлены')
            except Exception as e:
                messages.error(request, f'данные записи {obj.id} не обновлены {e}')

    def _get_admin_return_url(self, request, selected_ids=None):
        try:
            admin_url = reverse('admin:ProjectTDL_tasknode_changelist')
        except Exception as e:
            logger.error(f"Ошибка получения URL админки: {e}")
            return None

        params = {}
        for key, value in request.GET.items():
            if key in ['action', 'select_across', '_popup', '_to_field', '_changelist_filters']:
                continue
            if key.startswith('_') or key in ['select_across']:
                continue
            if key in request.GET.lists():
                values = request.GET.getlist(key)
                if len(values) > 1:
                    params[key] = values
                elif values:
                    params[key] = values[0]
            else:
                params[key] = value

        if selected_ids:
            params['id__in'] = ','.join(map(str, selected_ids))

        changelist_filters = request.GET.get('_changelist_filters')
        if changelist_filters:
            try:
                filter_params = parse_qs(changelist_filters)
                for key, values in filter_params.items():
                    if key not in params:
                        if len(values) == 1:
                            params[key] = values[0]
                        else:
                            params[key] = values
            except Exception:
                pass

        if params:
            query_parts = []
            for key, value in params.items():
                if isinstance(value, list):
                    for v in value:
                        query_parts.append(f"{key}={v}")
                else:
                    query_parts.append(f"{key}={value}")
            query_string = '&'.join(query_parts)
            admin_url = f"{admin_url}?{query_string}"

        admin_url = request.build_absolute_uri(admin_url)
        return admin_url

    @admin.action(description='Сгенерировать HTML отчет')
    def generate_html_report(self, request, queryset):
        try:
            task_count = queryset.count()
            if task_count == 0:
                messages.warning(request, "Не выбрано ни одной задачи для отчета")
                return None

            tasks = queryset.select_related(
                'project_site', 'building_number__name',
                'design_chapter', 'contractor', 'status', 'category', 'contract'
            ).prefetch_related('due_date_history')

            task_ids = list(queryset.values_list('id', flat=True))
            admin_url = self._get_admin_return_url(request, task_ids)

            logger.info(f"Генерация отчета: пользователь {request.user}, задач: {task_count}, "
                        f"выбранные ID: {task_ids[:10]}{'...' if len(task_ids) > 10 else ''}")

            html_report = ReportGenerator.generate_html_report(
                tasks, request, admin_url=admin_url
            )

            response = HttpResponse(html_report, content_type='text/html')
            response['Content-Disposition'] = 'inline; filename="tasks_report.html"'
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'

            logger.info(f"Отчет успешно сгенерирован: {task_count} задач")
            return response

        except Exception as e:
            logger.error(f'Ошибка при генерации отчета: {str(e)}', exc_info=True)
            self.message_user(request, f'Ошибка при генерации отчета: {str(e)}', level=messages.ERROR)
            return None

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)

        if hasattr(response, 'context_data'):
            response.context_data['report_actions_info'] = {
                'generate_report': 'Создает компактный отчет в новой вкладке',
            }

        try:
            qs = response.context_data['cl'].queryset
        except (AttributeError, KeyError):
            return response

        pivot_table_list = []
        for name, _column in zip(StaticFilterSettings.pivot_columns_names,
                                 StaticFilterSettings.pivot_columns_values):
            pivot_table1 = {"name": name,
                            'table': create_pivot_table(TaskNode, qs, StaticFilterSettings.replaced_list, _column)}
            pivot_table_list.append(pivot_table1)

        response.context_data['pivot_table_list'] = pivot_table_list
        return response

    class Media(object):
        # js подключается глобально через jazzmin custom_js (jasmin.py) — не дублируем
        css = {
            'all': ('admin/admin_css_v2.css',)
        }


@admin.register(DesignChapter)
class DesignChapterAdmin(ImportExportModelAdmin):
    actions = [duplicate_event]
    resource_classes = [DesignChapterResource]
    list_display = get_standard_display_list(DesignChapter)