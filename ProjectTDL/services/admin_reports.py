# -*- coding: utf-8 -*-
"""Отчёты и URL-хелперы админки задач (блок 5; переезд из admin без смены поведения)."""
import logging
from urllib.parse import parse_qs

from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse

logger = logging.getLogger(__name__)


def build_admin_return_url(request, selected_ids=None):
    """URL возврата в changelist с текущими фильтрами + id__in выбранных.

    Служебные GET-параметры (action, _*, select_across) отбрасываются.
    """
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

    return request.build_absolute_uri(admin_url)


def report_action_response(modeladmin, request, queryset, *, generator,
                           filename, empty_message, log_label):
    """Общий скелет экшенов «HTML-отчёт / протокол»: пусто, сборка, файл.

    Сообщения пользователю и имена файлов — как раньше у каждого экшена.
    Возвращает HttpResponse или None (пусто/ошибка).
    """
    task_count = queryset.count()
    if task_count == 0:
        messages.warning(request, empty_message)
        return None

    tasks = queryset.select_related(
        'project_site', 'building_number__name',
        'design_chapter', 'contractor', 'status', 'category', 'contract'
    ).prefetch_related('due_date_history')

    task_ids = list(queryset.values_list('id', flat=True))
    admin_url = build_admin_return_url(request, task_ids)

    logger.info(f"Генерация отчета ({log_label}): пользователь {request.user}, "
                f"задач: {task_count}, "
                f"выбранные ID: {task_ids[:10]}{'...' if len(task_ids) > 10 else ''}")
    try:
        html_report = generator(tasks, request, admin_url=admin_url)
    except Exception as e:
        logger.error(f'Ошибка при генерации {log_label}: {str(e)}', exc_info=True)
        modeladmin.message_user(
            request, f'Ошибка при генерации {log_label}: {str(e)}',
            level=messages.ERROR)
        return None

    response = HttpResponse(html_report, content_type='text/html')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'

    logger.info(f"Отчет ({log_label}) успешно сгенерирован: {task_count} задач")
    return response
