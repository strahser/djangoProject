# -*- coding: utf-8 -*-
"""Фазы custom_task_view (блок 29/B7; переезд из views без смены поведения).

custom_task_view (157 строк) состоял из фаз: разбор фильтров, персист
сортировки, построение таблицы, пивоты, xlsx-экспорт, настройки, контекст.
Здесь — шаги; во view остаются ветвление POST и сборка контекста.
"""
import pandas as pd
from django.contrib import messages
from django.http import HttpResponse
from django_tables2 import RequestConfig

from AdminUtils import get_standard_display_list
from ProjectTDL.forms import TaskFilterForm
from ProjectTDL.models import TaskNode, UserSettings
from ProjectTDL.Tables import (
    TaskNodeTable, StaticFilterSettings, create_filter_qs, data_filter_qs,
    order_qs_hierarchical,
)
from ProjectTDL.services.task_filters import get_filter_state, task_subtree_qs
from services.DataFrameRender.RenderDfFromModel import (
    renamed_dict, create_df_from_model,
)


def resolve_list_request(request):
    """Фильтры + queryset + форма списка (фаза 1 custom_task_view)."""
    initial = {}
    filter_state = None
    if request.method == 'GET':
        filter_state = get_filter_state(getattr(request, 'user', None))
        if filter_state:
            initial = {k: v for k, v in (filter_state.params or {}).items() if v}

    filter_dict = create_filter_qs(request, StaticFilterSettings.filtered_value_list)
    if not filter_dict and initial:
        filter_dict = create_filter_qs(
            request, StaticFilterSettings.filtered_value_list, data=initial)
    date_filter = data_filter_qs(
        request, 'due_date', data=initial if not request.POST else None)
    qs = task_subtree_qs(filter_dict, date_filter)
    form = TaskFilterForm(request.POST or None, initial=initial)
    return {
        'qs': qs, 'form': form, 'initial': initial,
        'filter_dict': filter_dict, 'filter_state': filter_state,
    }


def apply_table_sort(request):
    """Персист сортировки таблицы (фаза 2): ?sort > сохранённая > '-id'.

    Мутирует request.GET (RequestConfig читает сортировку оттуда) — как было.
    """
    url_sort = request.GET.get('sort', '')
    us = UserSettings.objects.filter(user=request.user).first() \
        if request.user.is_authenticated else None
    if request.user.is_authenticated:
        if url_sort:
            if us is None:
                us = UserSettings.objects.create(
                    user=request.user, table_sort=url_sort[:32])
            elif us.table_sort != url_sort:
                us.table_sort = url_sort[:32]
                us.save()
        else:
            eff_sort = (us.table_sort if us else '') or '-id'
            q = request.GET.copy()
            q['sort'] = eff_sort
            request.GET = q
    elif not url_sort:
        q = request.GET.copy()
        q['sort'] = '-id'
        request.GET = q


def build_task_table(request, qs):
    """Таблица-дерево с плоской сортировкой только корней (фаза 3).

    Возвращает (table, qs): при явной сортировке qs пересобирается
    иерархически (корни по ключу, поддеревья MPTT-порядком).
    """
    table = TaskNodeTable(qs)
    table.view_mode = 'tree'
    RequestConfig(request, paginate=False).configure(table)
    if table.order_by:
        # Плоская сортировка рвёт дерево (дочерние отрываются от родителей,
        # подзадача выглядит «отдельной задачей»): сортируем только корни
        # выборки, поддеревья идут MPTT-порядком. Состояние заголовков
        # сохраняем напрямую в _order_by, чтобы не пересортировать строки.
        sort_by = table.order_by
        qs = order_qs_hierarchical(qs, [str(o) for o in sort_by])
        table = TaskNodeTable(qs)
        table.view_mode = 'tree'
        table._order_by = sort_by
    return table, qs


def list_tree_roots():
    """Корни-таски для сайдбара дерева."""
    return TaskNode.objects.filter(
        parent__isnull=True, node_type='task').select_related(
        'project_site', 'status', 'contractor').prefetch_related('children')


def build_pivot_tables(qs):
    """Пивоты по колонкам StaticFilterSettings (POST submit)."""
    from services.DataFrameRender.RenderDfFromModel import create_pivot_table
    out = []
    for name, column in zip(StaticFilterSettings.pivot_columns_names,
                            StaticFilterSettings.pivot_columns_values):
        out.append({
            'name': name,
            'table': create_pivot_table(
                TaskNode, qs, StaticFilterSettings.replaced_list, column),
        })
    return out


def export_tasks_xlsx(request, qs):
    """XLSX-выгрузка выборки (POST save_attachments)."""
    df_initial = create_df_from_model(TaskNode, qs)
    df_initial['project_site'] = df_initial['project_site'].apply(
        lambda x: getattr(x, 'name'))
    df_initial = df_initial.sort_values('project_site')
    df_export = df_initial \
        .filter(get_standard_display_list(
            TaskNode, excluding_list=StaticFilterSettings.export_excluding_list)) \
        .rename(renamed_dict(TaskNode), axis='columns') \
        .fillna('')
    messages.success(
        request,
        f"успешно экспортировано {df_export.shape[0]} строк {df_export.shape[1]} столбцов")
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Задачи.xlsx"'
    writer = pd.ExcelWriter(response, engine='xlsxwriter')
    df_export.to_excel(writer, sheet_name='Задачи', index=False, freeze_panes=(1, 1))
    workbook = writer.book
    worksheet = writer.sheets['Задачи']
    column_settings = [{'header': column} for column in df_export]
    (max_row, max_col) = df_export.shape
    worksheet.add_table(0, 0, max_row, max_col - 1,
                        {'columns': column_settings,
                         'banded_columns': True,
                         'name': 'Задачи',
                         'autofilter': True,
                         'style': 'Table Style Light 8'})
    writer.close()
    return response


def user_settings_dict(user):
    """Настройки таблицы пользователя (дефолты для анонима/без строки)."""
    settings = {
        'inherit_props': False,
        'new_task_position': 'bottom',
        'default_tree_view': False,
        'default_project_site': False,
        'default_building': False,
        'default_category': False,
        'default_status': False,
        'default_contractor': False,
        'column_visibility': {},
        'column_widths': {},
        'column_order': [],
        'panel_fields': {},
        'page_length': None,
        'table_sort': '',
        'auto_save': True,
        'active_project_id': '',
    }
    if getattr(user, 'is_authenticated', False):
        us = UserSettings.objects.filter(user=user).first()
        if us:
            settings = {
                'inherit_props': us.inherit_props,
                'new_task_position': us.new_task_position,
                'default_tree_view': us.default_tree_view,
                'default_building': us.default_building,
                'default_category': us.default_category,
                'default_status': us.default_status,
                'default_contractor': us.default_contractor,
                'column_visibility': us.column_visibility or {},
                'column_widths': us.column_widths or {},
                'column_order': us.column_order or [],
                'panel_fields': us.panel_fields or {},
                'page_length': us.page_length,
                'table_sort': us.table_sort or '',
                'auto_save': us.auto_save,
                'active_project_id': us.active_project_id or '',
            }
    # FACT: default_project_site в сохранённых настройках НЕ читается
    # (в dict'е из БД его нет — остаётся дефолт False). Пин факта, не идеала.
    return settings


def filter_dropdowns():
    """Справочники выпадающих фильтров списка."""
    from ProjectContract.models import Contractor
    from StaticData.models import (
        BuildingNumber, BuildingType, Category, DesignChapter, ProjectSite,
        Status,
    )
    return {
        'all_contractors': Contractor.objects.all().order_by('name'),
        'all_statuses': Status.objects.all().order_by('name'),
        'all_categories': Category.objects.all().order_by('name'),
        'all_project_sites': ProjectSite.objects.all().order_by('name'),
        'all_buildings': BuildingNumber.objects.all().order_by('building_number'),
        'all_building_types': BuildingType.objects.all().order_by('name'),
        'all_design_chapters': DesignChapter.objects.all().order_by('short_name'),
    }
