# ProjectTDL/reports.py
from django.utils import timezone
from html.parser import HTMLParser
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import mark_safe
import locale

# Настройка локали для форматирования чисел
try:
    locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'Russian_Russia.1251')
    except:
        locale.setlocale(locale.LC_ALL, '')


class HTMLFilter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = ""

    def handle_data(self, data):
        self.text += data


def html_convert(data):
    """Конвертация HTML в текст"""
    if data:
        f = HTMLFilter()
        f.feed(data)
        return f.text
    else:
        return ""


def format_currency(value, decimal_places=2):
    """Форматирование денежных значений"""
    try:
        if value is None:
            return f"0.{'0' * decimal_places}"

        value = float(value)
        if decimal_places == 2:
            # Форматирование с разделителями тысяч
            return f"{value:,.2f}".replace(",", " ").replace(".", ",")
        elif decimal_places == 3:
            return f"{value:,.3f}".replace(",", " ").replace(".", ",")
        else:
            return f"{value:,.2f}".replace(",", " ").replace(".", ",")
    except:
        return f"0.{'0' * decimal_places}"


class ReportGenerator:
    """Генератор отчетов по задачам"""

    @staticmethod
    def generate_html_report(tasks_queryset, request=None, admin_url=None, use_layout=False):
        """Генерация HTML отчета по выбранным задачам

        Args:
            tasks_queryset: QuerySet задач
            request: HTTP запрос (для построения абсолютных URL)
            admin_url: URL для возврата в админку с фильтрами
            use_layout: Использовать ли основной layout приложения
        """
        html_content = []

        # Собираем данные для summary
        total_price_all = 0
        total_subtasks_all = 0
        total_history_all = 0

        # Статусы для подсчета
        status_counts = {
            'active': 0,
            'completed': 0,
            'overdue': 0
        }

        # Получаем все выбранные ID для информации
        selected_task_ids = list(tasks_queryset.values_list('id', flat=True))

        for task in tasks_queryset:
            # Определяем класс статуса для CSS
            status_class = 'active'
            if task.status and ('выполнена' in task.status.name.lower() or 'завершена' in task.status.name.lower()):
                status_class = 'completed'
            elif task.status and 'просроч' in task.status.name.lower():
                status_class = 'overdue'

            # Обновляем счетчики статусов
            if status_class == 'active':
                status_counts['active'] += 1
            elif status_class == 'completed':
                status_counts['completed'] += 1
            elif status_class == 'overdue':
                status_counts['overdue'] += 1

            # Основная информация о задаче
            task_info = {
                'id': task.id,
                'name': task.name,
                'project': task.project_site.name if task.project_site else '-',
                'sub_project': task.sub_project.name if task.sub_project else '-',
                'building': f"{task.building_number.name.name} ({task.building_number.building_number})"
                if task.building_number and task.building_number.name else '-',
                'design_chapter': task.design_chapter.name if task.design_chapter else '-',
                'contractor': task.contractor.name if task.contractor else '-',
                'status': task.status.name if task.status else '-',
                'status_class': status_class,
                'category': task.category.name if task.category else '-',
                'price': float(task.price) if task.price else 0.0,
                'price_display': format_currency(task.price, 2) if task.price else '0,00',
                'due_date': task.due_date.strftime('%d.%m.%Y') if task.due_date else '-',
                'description': mark_safe(task.description) if task.description else mark_safe(
                    '<span class="no-data">Нет описания</span>'),
                'created': task.creation_stamp.strftime('%d.%m.%Y %H:%M'),
                'updated': task.update_stamp.strftime('%d.%m.%Y %H:%M'),
            }

            # Подзадачи
            subtasks = task.subtask_set.all()
            subtasks_data = []
            subtask_total = 0
            for subtask in subtasks:
                subtasks_data.append({
                    'name': subtask.name,
                    'description': mark_safe(subtask.description) if subtask.description else '',
                    'price': format_currency(subtask.price, 3) if subtask.price else '0,000',
                    'due_date': subtask.due_date.strftime('%d.%m.%Y') if subtask.due_date else '-',
                    'created': subtask.creation_stamp.strftime('%d.%m.%Y %H:%M'),
                })
                if subtask.price:
                    subtask_total += float(subtask.price)

            # История изменений сроков
            history = task.due_date_history.all()
            history_data = []
            for record in history:
                history_data.append({
                    'old_date': record.old_due_date.strftime('%d.%m.%Y') if record.old_due_date else '-',
                    'new_date': record.new_due_date.strftime('%d.%m.%Y') if record.new_due_date else '-',
                    'change_date': record.change_date.strftime('%d.%m.%Y %H:%M'),
                    'changed_by': record.changed_by.username if record.changed_by else '-',
                })

            total_price_all += task_info['price']
            total_subtasks_all += len(subtasks)
            total_history_all += len(history)

            html_content.append({
                'task': task_info,
                'subtasks': subtasks_data,
                'subtask_total': subtask_total,
                'subtask_total_formatted': format_currency(subtask_total, 3),
                'history': history_data,
                'subtask_count': len(subtasks),
                'history_count': len(history),
            })

        # Создаем URL для возврата на главную страницу
        home_url = None
        if request:
            try:
                home_url = reverse('custom_task_view')
                home_url = request.build_absolute_uri(home_url)
            except:
                home_url = None

        # Если admin_url не передан, создаем его с учетом текущих параметров
        if not admin_url and request:
            try:
                # Базовый URL админки
                admin_url = reverse('admin:ProjectTDL_task_changelist')

                # Добавляем параметры для сохранения выбранных задач
                if selected_task_ids:
                    # Вместо id__in используем стандартный формат админки
                    admin_url += f'?id__in={",".join(map(str, selected_task_ids))}'

                admin_url = request.build_absolute_uri(admin_url)
            except:
                admin_url = None

        # Форматируем общую стоимость
        total_price_all_formatted = format_currency(total_price_all, 2)

        # Определяем, какой шаблон использовать
        if use_layout:
            template_name = 'ProjectTDL/report_with_layout.html'
        else:
            template_name = 'ProjectTDL/report.html'

        # Подготовка контекста для шаблона
        context = {
            'current_date': timezone.now().strftime('%d.%m.%Y %H:%M'),
            'task_count': len(html_content),
            'selected_task_count': len(selected_task_ids),
            'selected_task_ids': selected_task_ids,
            'total_price_all': total_price_all,
            'total_price_all_formatted': total_price_all_formatted,
            'total_subtasks_all': total_subtasks_all,
            'total_history_all': total_history_all,
            'status_counts': status_counts,
            'html_content': html_content,
            'download_timestamp': timezone.now().strftime("%Y%m%d_%H%M"),
            'admin_url': admin_url,
            'home_url': home_url,
            'use_layout': use_layout,
        }

        # Рендерим шаблон
        html_report = render_to_string(template_name, context)

        return html_report