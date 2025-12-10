import logging
from urllib.parse import urlencode, parse_qs

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
from ProjectContract.models import Contract, ContractPayments, PaymentCalendar, ConcretePaymentCalendar
from ProjectTDL.Tables import StaticFilterSettings
from ProjectTDL.models import Task, SubTask, TaskDueDateHistory
from ProjectTDL.reports import ReportGenerator, html_convert
from StaticData.models import DesignChapter
from services.DataFrameRender.RenderDfFromModel import create_pivot_table

logger = logging.getLogger(__name__)


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


class TaskDueDateHistoryInline(admin.StackedInline):
    """Inline для отображения истории изменений сроков выполнения задачи"""
    model = TaskDueDateHistory
    extra = 0
    max_num = 0  # Запрещаем добавление новых записей через админку
    can_delete = False
    readonly_fields = ['old_due_date', 'new_due_date', 'change_date', 'changed_by']

    def has_add_permission(self, request, obj=None):
        return False


class TaskInline(admin.StackedInline):
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


excluding_list = [Task, Contract, DesignChapter, ContractPayments, PaymentCalendar, ConcretePaymentCalendar]


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
    additional_list = ['creation_stamp', 'add_emails_button', 'add_report_button']
    actions = [duplicate_event, 'html_replace', 'generate_html_report', 'generate_html_report_with_layout']
    list_display_links = ('id',)
    list_display = get_standard_display_list(Task, excluding_list=excluding_list, additional_list=additional_list)
    list_editable = ('status', 'category', 'price', 'due_date',)
    list_filter = ['project_site__name', 'sub_project', 'building_number',
                   'status', 'category', 'contractor', 'contract', ]
    search_fields = ['name', 'project_site__name', 'sub_project__name', 'contractor__name']
    inlines = [TaskInline, EmailInline, TaskDueDateHistoryInline]
    resource_classes = [TaskResource]
    list_per_page = 20
    actions_on_bottom = True
    list_footer = True
    change_list_template = 'jazzmin/admin/change_list.html'

    def add_emails_button(self, obj):
        url = reverse('select_email', args=[obj.pk])
        return format_html(f'<a href="{url}" class="button">✉️</a>')

    add_emails_button.short_description = 'Email'

    def add_report_button(self, obj):
        url = reverse('generate_custom_report') + f'?task_ids={obj.pk}'
        return format_html(f'<a href="{url}" class="button" target="_blank" title="Сгенерировать отчет">📊</a>')

    add_report_button.short_description = 'Отчет'

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
        return obj.design_chapter.name if obj.design_chapter else ''

    @admin.action(description='Заменить HTML текст')
    def html_replace(modeladmin, request, queryset):
        for object in queryset:
            try:
                object.description = html_convert(object.description)
                object.save()
                messages.success(request, f'данные записи {object.id} обновлены')
            except Exception as e:
                messages.error(request, f'данные записи {object.id} не обновлены {e}')

    def _get_admin_return_url(self, request, selected_ids=None):
        """Создание URL для возврата в админку с сохранением всех параметров"""
        # Базовый URL для списка задач в админке
        try:
            admin_url = reverse('admin:ProjectTDL_task_changelist')
        except Exception as e:
            logger.error(f"Ошибка получения URL админки: {e}")
            return None

        # Копируем текущие параметры запроса
        params = {}

        # Обрабатываем GET параметры
        for key, value in request.GET.items():
            # Пропускаем служебные параметры Django admin
            if key in ['action', 'select_across', '_popup', '_to_field', '_changelist_filters']:
                continue

            # Пропускаем параметры, связанные с выбором в action
            if key.startswith('_') or key in ['select_across']:
                continue

            # Для параметров фильтрации, которые могут быть списками
            if key in request.GET.lists():
                values = request.GET.getlist(key)
                if len(values) > 1:
                    params[key] = values
                elif values:
                    params[key] = values[0]
            else:
                params[key] = value

        # Если переданы selected_ids, добавляем их для сохранения выбора
        if selected_ids:
            # Используем параметр, который понимает Django admin для фильтрации по ID
            params['id__in'] = ','.join(map(str, selected_ids))

        # Добавляем параметры фильтрации, если они есть в сессии
        changelist_filters = request.GET.get('_changelist_filters')
        if changelist_filters:
            try:
                # Парсим фильтры из параметра
                filter_params = parse_qs(changelist_filters)
                for key, values in filter_params.items():
                    if key not in params:  # Не перезаписываем существующие
                        if len(values) == 1:
                            params[key] = values[0]
                        else:
                            params[key] = values
            except Exception as e:
                logger.error(f"Ошибка парсинга фильтров: {e}")

        # Формируем строку запроса
        if params:
            # Обрабатываем списки значений
            query_parts = []
            for key, value in params.items():
                if isinstance(value, list):
                    for v in value:
                        query_parts.append(f"{key}={v}")
                else:
                    query_parts.append(f"{key}={value}")

            query_string = '&'.join(query_parts)
            admin_url = f"{admin_url}?{query_string}"

        # Делаем абсолютный URL
        admin_url = request.build_absolute_uri(admin_url)

        return admin_url

    @admin.action(description='📊 Сгенерировать HTML отчет')
    def generate_html_report(self, request, queryset):
        """Генерация HTML отчета по выбранным задачам (основной вариант)"""
        try:
            # Проверяем количество выбранных задач
            task_count = queryset.count()
            if task_count == 0:
                messages.warning(request, "Не выбрано ни одной задачи для отчета")
                return None

            # Предварительно загружаем связанные данные для оптимизации
            tasks = queryset.select_related(
                'project_site', 'sub_project', 'building_number__name',
                'design_chapter', 'contractor', 'status', 'category', 'contract'
            ).prefetch_related('subtask_set', 'due_date_history')

            # Получаем ID выбранных задач
            selected_ids = list(queryset.values_list('id', flat=True))

            # Создаем URL для возврата в админку с сохранением всех параметров
            admin_url = self._get_admin_return_url(request, selected_ids)

            # Логируем информацию о генерации отчета
            logger.info(f"Генерация отчета: пользователь {request.user}, задач: {task_count}, "
                        f"выбранные ID: {selected_ids[:10]}{'...' if len(selected_ids) > 10 else ''}")

            # Получаем HTML отчет, передаем admin_url
            html_report = ReportGenerator.generate_html_report(
                tasks,
                request,
                admin_url=admin_url,
                use_layout=False  # Основной шаблон - простой отчет без layout
            )

            # Создаем HTTP ответ с HTML содержимым
            response = HttpResponse(html_report, content_type='text/html')
            response['Content-Disposition'] = 'inline; filename="tasks_report.html"'

            # Добавляем заголовки для кэширования
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'

            # Логируем успешную генерацию
            logger.info(f"Отчет успешно сгенерирован: {task_count} задач")

            return response

        except Exception as e:
            logger.error(f'Ошибка при генерации отчета: {str(e)}', exc_info=True)
            self.message_user(
                request,
                f'Ошибка при генерации отчета: {str(e)}',
                level=messages.ERROR
            )
            return None

    @admin.action(description='📊 Сгенерировать отчет с layout')
    def generate_html_report_with_layout(self, request, queryset):
        """Генерация HTML отчета с использованием основного layout приложения"""
        try:
            # Проверяем количество выбранных задач
            task_count = queryset.count()
            if task_count == 0:
                messages.warning(request, "Не выбрано ни одной задачи для отчета")
                return None

            # Предварительно загружаем связанные данные для оптимизации
            tasks = queryset.select_related(
                'project_site', 'sub_project', 'building_number__name',
                'design_chapter', 'contractor', 'status', 'category', 'contract'
            ).prefetch_related('subtask_set', 'due_date_history')

            # Получаем ID выбранных задач
            selected_ids = list(queryset.values_list('id', flat=True))

            # Создаем URL для возврата в админку с сохранением всех параметров
            admin_url = self._get_admin_return_url(request, selected_ids)

            # Получаем HTML отчет с layout
            html_report = ReportGenerator.generate_html_report(
                tasks,
                request,
                admin_url=admin_url,
                use_layout=True  # Отчет с layout приложения
            )

            # Создаем HTTP ответ с HTML содержимым
            response = HttpResponse(html_report, content_type='text/html')
            response['Content-Disposition'] = 'inline; filename="tasks_report_layout.html"'

            return response

        except Exception as e:
            logger.error(f'Ошибка при генерации отчета с layout: {str(e)}', exc_info=True)
            self.message_user(
                request,
                f'Ошибка при генерации отчета с layout: {str(e)}',
                level=messages.ERROR
            )
            return None

    def changelist_view(self, request, extra_context=None):
        """Переопределение changelist_view для добавления pivot таблиц"""
        response = super().changelist_view(
            request,
            extra_context=extra_context,
        )

        # Добавляем информацию о доступных действиях с отчетами
        if hasattr(response, 'context_data'):
            response.context_data['report_actions_info'] = {
                'generate_report': 'Создает компактный отчет в новой вкладке',
                'generate_report_with_layout': 'Создает отчет в стиле приложения',
            }

        try:
            qs = response.context_data['cl'].queryset
        except (AttributeError, KeyError):
            return response

        # Генерация pivot таблиц
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
        css = {
            'all': ('admin/css/admin_custom.css',)
        }


@admin.register(DesignChapter)
class DesignChapterAdmin(ImportExportModelAdmin):
    actions = [duplicate_event]
    resource_classes = [DesignChapterResource]
    list_display = get_standard_display_list(DesignChapter)