import os
from pprint import pprint
import pandas as pd
import datetime
import django_tables2 as tables
from django.db.models import QuerySet
from django.http import HttpResponse
from django.urls import reverse_lazy, reverse
from django.utils.safestring import mark_safe
from django_tables2 import LazyPaginator
from pretty_html_table import pretty_html_table

from AdminUtils import get_standard_display_list
from ProjectContract.models import Contractor
from ProjectTDL.models import TaskNode
from StaticData.models import Status
from services.DataFrameRender.RenderDfFromModel import create_df_from_model, renamed_dict
from services.Downloads.ExcelDownload import df_to_excel_in_memory, result_to_excel_add_table
import re


# region Table
class StaticFilterSettings:
    filtered_value_list = ['project_site', 'building_number', 'status', 'category', 'contractor', ]
    replaced_list = ['contractor', 'contract', 'category', 'status']
    pivot_columns_values = ['contract', 'status', 'category', ]
    pivot_columns_names = ['Договор', 'Статус', 'Категория']
    export_excluding_list = ['price', 'contract', 'owner', 'description']


def create_filter_qs(request, filtered_value_list, data=None) -> dict:
    source = data if data is not None else request.POST
    filter_dict = {}
    for field_name in filtered_value_list:
        _data = source.getlist(field_name) if hasattr(source, 'getlist') else [source.get(field_name)]
        if _data:
            _data = [v for v in _data if v]
            if _data:
                filter_dict[f'{field_name}__id__in'] = _data
    return filter_dict


def data_filter_qs(request, datefield, data=None):
    source = data if data is not None else request.POST
    get_date = source.get(datefield)
    res_dict = {}
    _today = datetime.date.today()
    if get_date:
        if get_date == 'today':
            res_dict[f'{datefield}'] = _today
        if get_date == 'week':
            res_dict[f'{datefield}__gte'] = _today
        if get_date == 'past':
            res_dict[f'{datefield}__lt'] = _today
    return res_dict


def add_period_data_to_column(df_cash_flow: pd.DataFrame, freq='d'):
    df_cash_flow['creation_stamp'] = df_cash_flow['creation_stamp'].apply(
        lambda x: pd.to_datetime(x, utc=True).tz_localize(None).date())
    df_cash_flow['due_date'] = df_cash_flow['due_date'].apply(
        lambda x: pd.to_datetime(x, utc=True).tz_localize(None).date()
    )
    df_cash_flow['date_range'] = df_cash_flow.apply(
        lambda x: pd.date_range(x['creation_stamp'], x['due_date'], freq=freq).date, axis=1)
    return df_cash_flow


def create_multithreading_period_data(df_day, df_month, df_year):
    renamed_month_dict = {1: 'январь', 2: 'февраль', 3: 'март', 4: 'апрель'}
    headers1 = [
        (val3, val2, val1) for val1, val2, val3 in zip(
            df_day.iloc[0], df_month.iloc[0].replace(renamed_month_dict), df_year.iloc[0]
        )
    ]
    headers = df_day.iloc[0]
    df_day.columns = pd.MultiIndex.from_tuples(headers1) if headers1 else headers
    return df_day


def add_bar_to_df_columns(df_day):
    return df_day.mask(df_day.notnull(), '&#9644;&#9644;')


def get_period_data(df_cash_flow, start, end) -> pd.DataFrame:
    df_cash_flow_ = add_period_data_to_column(df_cash_flow)

    dt_range = pd.date_range(start=start,
                             end=end,
                             normalize=True,
                             freq='1d'
                             )
    df_day = dt_range.day.to_frame().T
    df_month = dt_range.month.to_frame().T
    df_year = dt_range.year.to_frame().T
    df_cash_flow = df_cash_flow[['id', 'name', 'due_date']]
    res = pd.concat([df_cash_flow, df_day], axis=1, ignore_index=True)

    return df_cash_flow_


def create_cash_flow_chart(qs, freq: str = 'd') -> str:
    GANT_DF_PROPERTY = dict(
        classes="table table-hover",
        table_id='GantTable',
        index=False,
        show_dimensions=False,
        render_links=True,
        justify='center',
        escape=False,
        border=2,
    )
    df_cash_flow = create_df_from_model(TaskNode, qs, skip_time_stamps=False) \
        .drop(['description', 'building_number', 'design_chapter', 'update_stamp'], axis=1)
    per1 = add_period_data_to_column(df_cash_flow, freq)
    per1['tim_dif'] = per1['due_date'] - per1['creation_stamp']
    per1['tim_dif'] = per1['tim_dif'] / pd.Timedelta(days=1)
    per1['tim_dif'] = per1['tim_dif'].astype(int)
    max_value = per1["due_date"].max()
    min_value = per1["creation_stamp"].min()
    all_periods = pd.date_range(min_value, max_value, freq=freq)
    all_periods = [val.date() for val in all_periods]
    gant_list = []
    for index, row in per1.iterrows():
        for data in row["date_range"]:
            if len(row['date_range']) > 0 and row['price']:
                res = round(row['price'] / len(row['date_range']), 2)
                df = pd.DataFrame({'id': [row['id']], (data.year, data.month, data.day): [res]})
                gant_list.append(df)
            elif row["due_date"] not in all_periods:
                res = row["price"]
                df = pd.DataFrame({'id': [row['id']], (data.year, data.month, all_periods[0]): [res]})
                gant_list.append(df)
    res = pd.concat(gant_list)
    res = res.pivot_table(index='id', aggfunc="sum").reset_index()
    # res = res.replace(0, '&#9644;&#9644;')
    res = res.replace(0, '')
    df_cash_flow_columns = ['id', 'name', 'contractor', 'status', 'price',
                            'creation_stamp', 'due_date', 'tim_dif',
                            ]
    fitret_df_cash_flow = df_cash_flow[df_cash_flow_columns]

    res = fitret_df_cash_flow.merge(res, how='left', on='id', )
    res.columns = [(val, '', '') if not isinstance(val, tuple) else val for val in res]
    columns = pd.MultiIndex.from_tuples([val for val in res.columns])
    res.columns = columns
    res = res.fillna('').to_html(**GANT_DF_PROPERTY)
    # res =  pretty_html_table.build_table(res, 'blue_dark', escape=False, )
    return res


# endregion
def rows_highlighter(**kwargs):
    selected_rows = kwargs["table"].selected_rows
    if selected_rows and kwargs["record"].pk in selected_rows:
        return "highlight-me"
    return ""


class CheckBoxColumnWithName(tables.CheckBoxColumn):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attrs = {"td__input": {"class": "form-check-input task-checkbox"}}


class TaskNodeTable(tables.Table):
    name = tables.LinkColumn('task_detail', args=[tables.A('pk')], default='Link', empty_values=())
    selection = CheckBoxColumnWithName(
        verbose_name=mark_safe('<input type="checkbox" class="form-check-input" id="checkAll">'), accessor="pk",
        orderable=False,
    )

    def render_name(self, record):
        # Иконка/отступ для дерева: родители (есть дети) — папка + стрелка; подзадачи — отступ
        try:
            has_children = TaskNode.objects.filter(parent_id=record.pk).exists()
        except Exception:
            has_children = False
        depth = record.get_level() if hasattr(record, 'get_level') else 0
        indent = depth * 22
        view_mode = getattr(self, 'view_mode', 'flat')
        if has_children:
            # В дереве — стрелка раскрытия; в плоском списке только иконка папки
            toggle = ('<i class="bi bi-chevron-right small tree-toggle me-1" style="cursor:pointer;"></i>'
                      if view_mode == 'tree' else '')
            folder = '<i class="bi bi-folder2-open me-1" style="color:#ffc107;"></i>'
            cls = 'tree-name tree-parent-name'
            link_cls = 'fw-semibold'  # жирный — только для родителя
        else:
            toggle = ''
            folder = '<i class="bi bi-dot small text-muted me-1" style="width:1em;"></i>'
            cls = 'tree-name'
            link_cls = ''  # подзадачи — обычный вес
        return mark_safe(
            f'<span style="display:inline-flex;align-items:center;padding-left:{indent}px;">'
            f'{toggle}{folder}'
            f'<a href="{reverse("task_detail", args=[record.pk])}" class="{link_cls} text-decoration-none {cls}" '
            f'onclick="event.stopPropagation()">{record.name}</a></span>'
        )

    def render_contractor(self, record):
        return record.contractor.name if record.contractor else ''

    def render_building_number(self, record):
        return record.building_number.name.name if record.building_number and record.building_number.name else ''

    def render_project_site(self, record):
        return record.project_site.name if record.project_site else ''

    def render_category(self, record):
        return record.category.name if record.category else ''

    def render_contract(self, record):
        return record.contract.name if record.contract else ''

    def render_owner(self, record):
        return record.owner.username if record.owner else ''

    def render_description(self, record):
        if not record.description:
            return ''
        text = str(record.description)
        return text[:80] + ('…' if len(text) > 80 else '')

    def render_creation_stamp(self, record):
        return record.creation_stamp.strftime('%d.%m.%Y %H:%M') if record.creation_stamp else ''

    def render_update_stamp(self, record):
        return record.update_stamp.strftime('%d.%m.%Y %H:%M') if record.update_stamp else ''

    def render_status(self, record):
        return record.status.name if record.status else ''

    def render_due_date(self, record):
        return record.due_date.strftime('%d.%m.%Y') if record.due_date else ''

    def render_price(self, record):
        return f'{record.price:.2f} ₽' if record.price else ''

    class Meta:
        model = TaskNode
        template_name = "django_tables2/bootstrap_no_pag.html"
        exclude = ('lft', 'rght', 'level', 'tree_id', 'parent', 'node_type')
        row_attrs = {
            "data-id": lambda record: record.pk,
            "data-parent-id": lambda record: record.parent_id or '',
            "data-depth": lambda record: record.get_level() if hasattr(record, 'get_level') else 0,
            "data-has-children": lambda record: '1' if TaskNode.objects.filter(parent_id=record.pk).exists() else '0',
            "data-project-site-id": lambda record: record.project_site_id or '',
            "data-project-site-name": lambda record: record.project_site.name if record.project_site else '',
            "data-building-id": lambda record: record.building_number_id or '',
            "data-building-name": lambda record: record.building_number.name.name if record.building_number and record.building_number.name else '',
            "data-status-id": lambda record: record.status_id or '',
            "data-status-name": lambda record: record.status.name if record.status else '',
            "data-category-id": lambda record: record.category_id or '',
            "data-category-name": lambda record: record.category.name if record.category else '',
            "data-contractor-id": lambda record: record.contractor_id or '',
            "data-contractor-name": lambda record: record.contractor.name if record.contractor else '',
            "data-due-date": lambda record: record.due_date.strftime('%Y-%m-%d') if record.due_date else '',
            "data-price": lambda record: str(record.price) if record.price else '',
        }
        attrs = {"id": "TaskTable",
                 'class': 'table table-bordered',
                 'thead': {
                     'class': 'table-light',
                 },
                 }
        sequence = ("selection", "name", "...",)
