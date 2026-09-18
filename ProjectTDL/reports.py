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
    def _task_info(task):
        """Основная информация о задаче — единый словарь для всех форматов."""
        status_class = 'active'
        if task.status and ('выполнена' in task.status.name.lower() or 'завершена' in task.status.name.lower()):
            status_class = 'completed'
        elif task.status and 'просроч' in task.status.name.lower():
            status_class = 'overdue'
        return {
            'id': task.id,
            'name': task.name,
            'project': task.project_site.name if task.project_site else '-',
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
            'description_text': html_convert(task.description or ''),
            'created': task.creation_stamp.strftime('%d.%m.%Y %H:%M'),
            'updated': task.update_stamp.strftime('%d.%m.%Y %H:%M'),
        }

    @staticmethod
    def _email_excerpt(email, limit: int = 800) -> str:
        """Короткий текст письма: body_text из БД, иначе из HTML-файла на диске."""
        import re
        text = (getattr(email, 'body_text', '') or '').strip()
        if not text:
            try:
                text = (email.extract_body_text() or '').strip()
            except Exception:
                text = ''
        text = re.sub(r'\s+', ' ', text)
        return (text[:limit] + '…') if len(text) > limit else text

    @staticmethod
    def _protocol_item(task, selected_ids: set, meeting_day=None):
        """Одна строка протокола: задача + дерево + письма + переносы сроков."""
        from datetime import date as _date
        info = ReportGenerator._task_info(task)
        ancestors = list(task.get_ancestors())
        path = [a.name for a in ancestors]
        depth = sum(1 for a in ancestors if a.pk in selected_ids)
        due_raw = task.due_date
        is_closed = info['status_class'] == 'completed'
        is_overdue = bool(due_raw and meeting_day and due_raw < meeting_day and not is_closed)
        info['due_iso'] = due_raw.isoformat() if due_raw else ''
        # Подзадачи (дети первого уровня)
        children = task.get_children().filter(node_type='subtask').order_by('id') \
            if hasattr(task, 'get_children') else []
        subtasks = [{
            'name': st.name,
            'due_date': st.due_date.strftime('%d.%m.%Y') if st.due_date else '-',
            'status': st.status.name if st.status else '-',
            'is_closed': bool(st.status and (
                'выполнена' in st.status.name.lower() or 'завершена' in st.status.name.lower())),
        } for st in children]
        # Прикреплённые письма
        emails = []
        try:
            linked = task.emails.all().order_by('-email_stamp')[:5]
        except Exception:
            linked = []
        for em in linked:
            emails.append({
                'subject': em.subject or '(без темы)',
                'sender': em.sender or '—',
                'receiver': em.receiver or '—',
                'date': em.email_stamp.strftime('%d.%m.%Y %H:%M') if em.email_stamp else '—',
                'excerpt': ReportGenerator._email_excerpt(em),
            })
        # История переносов сроков
        history = list(task.due_date_history.all())
        moves = [{
            'old_date': r.old_due_date.strftime('%d.%m.%Y') if r.old_due_date else '—',
            'new_date': r.new_due_date.strftime('%d.%m.%Y') if r.new_due_date else '—',
            'change_date': r.change_date.strftime('%d.%m.%Y %H:%M'),
            'changed_by': r.changed_by.username if r.changed_by else '—',
        } for r in history]
        last = moves[0] if moves else None
        return {
            'task': info,
            'depth': depth,
            'path': path,
            'is_overdue': is_overdue,
            'is_closed': is_closed,
            'has_decision': bool(info.get('description_text')),
            'subtasks': subtasks,
            'emails': emails,
            'email_count': len(emails),
            'moves': moves,
            'moves_count': len(moves),
            'last_move': last,
        }

    @staticmethod
    def generate_protocol_report(tasks_queryset, request=None, admin_url=None, meeting_date=None):
        """Протокол совещания по выбранным задачам: повестка + решения + переносы.

        Задачи упорядочены деревом (родитель → дети), у каждой — описание-решение,
        прикреплённые письма (тексты) и история переносов сроков.
        """
        from datetime import date as _date
        if isinstance(meeting_date, _date):
            meeting_day = meeting_date
        else:
            meeting_day = _date.today()
        try:
            if not isinstance(meeting_date, _date) and meeting_date:
                meeting_day = _date.fromisoformat(str(meeting_date))
        except ValueError:
            pass
        items = []
        selected_ids = set(tasks_queryset.values_list('id', flat=True))
        ordered = tasks_queryset.order_by('tree_id', 'lft')
        for task in ordered:
            items.append(ReportGenerator._protocol_item(task, selected_ids, meeting_day))
        projects = sorted({it['task']['project'] for it in items if it['task']['project'] != '-'})
        chapters = sorted({it['task']['design_chapter'] for it in items
                           if it['task']['design_chapter'] != '-'})
        decisions = sum(1 for it in items if it['has_decision'])
        context = {
            'current_date': timezone.now().strftime('%d.%m.%Y %H:%M'),
            'meeting_date': meeting_day.strftime('%d.%m.%Y'),
            'meeting_date_iso': meeting_day.isoformat(),
            'projects': projects,
            'chapters': chapters,
            'items': items,
            'task_count': len(items),
            'with_emails': sum(1 for it in items if it['email_count']),
            'rescheduled': sum(1 for it in items if it['moves_count']),
            'total_moves': sum(it['moves_count'] for it in items),
            'overdue_count': sum(1 for it in items if it['is_overdue']),
            'closed_count': sum(1 for it in items if it['is_closed']),
            'decisions_count': decisions,
            'decision_percent': round(100 * decisions / len(items)) if items else 0,
            'download_timestamp': timezone.now().strftime('%Y%m%d_%H%M'),
            'admin_url': admin_url,
        }
        return render_to_string('ProjectTDL/protocol_report.html', context)

    @staticmethod
    def generate_html_report(tasks_queryset, request=None, admin_url=None):
        """Генерация HTML отчета по выбранным задачам

        Args:
            tasks_queryset: QuerySet задач
            request: HTTP запрос (для построения абсолютных URL)
            admin_url: URL для возврата в админку с фильтрами
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
            task_info = ReportGenerator._task_info(task)

            # Обновляем счетчики статусов
            if task_info['status_class'] == 'active':
                status_counts['active'] += 1
            elif task_info['status_class'] == 'completed':
                status_counts['completed'] += 1
            elif task_info['status_class'] == 'overdue':
                status_counts['overdue'] += 1

            # Подзадачи (TaskNode children)
            subtasks = getattr(task, 'get_children', lambda: [])()
            if callable(subtasks):
                subtasks = subtasks.filter(node_type='subtask') if hasattr(subtasks, 'filter') else []
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
                admin_url = reverse('admin:ProjectTDL_tasknode_changelist')

                # Добавляем параметры для сохранения выбранных задач
                if selected_task_ids:
                    # Вместо id__in используем стандартный формат админки
                    admin_url += f'?id__in={",".join(map(str, selected_task_ids))}'

                admin_url = request.build_absolute_uri(admin_url)
            except:
                admin_url = None

        # Форматируем общую стоимость
        total_price_all_formatted = format_currency(total_price_all, 2)

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
        }

        # Рендерим шаблон
        html_report = render_to_string(template_name, context)

        return html_report