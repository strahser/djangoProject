from django.shortcuts import render, redirect
from ProjectTDL.forms import EmailForm, TaskFilterForm
from ProjectTDL.models import Task
import pandas as pd
from ProjectTDL.querys.EmailCreate import parsing_form, parsing_email_data_to_form, add_form_data_to_data_base
from django.utils.safestring import mark_safe
from django_pandas.io import read_frame
from django.db import models


def get_standard_display_list(model, excluding_list: list[str] = None, additional_list: list[str] = None):
    additional_list = additional_list if additional_list else []
    excluding_list = excluding_list if excluding_list else []
    excluding_list = ["creation_stamp", 'update_stamp'] + excluding_list
    return [f.name for f in model._meta.fields if f.name not in excluding_list] + additional_list


def renamed_dict(model_type: models.Model) -> dict[str, str]:
    """переименовываем столбцы модели django согласно заданному verbose name """
    names = get_standard_display_list(model_type)
    res_dict = {}
    for val in names:
        try:
            res_dict[val] = model_type._meta.get_field(val).verbose_name
        except:
            pass
    return res_dict


def create_table_from_model(qs) -> pd.DataFrame:
    """создаем таблицу на основе модели django (выбираем все записи если qs не задан) через библиотеку
    django_pandas read_frame добавляем столбец с пустой ссылкой на id модели
    задаем id для data table рендера
    """
    df = read_frame(qs, verbose=True, datetime_index=False)
    return df


def df_html(df: pd.DataFrame, table_id="zero_config", index=False, formatters=None) -> str:
    """Обертка со стилями для экспорта дата фрейм в html"""
    return df.to_html(index=index, classes="table table-striped table-bordered ", border=1, render_links=True,
                      justify='center', escape=False, table_id=table_id, formatters=formatters)


FILTERED_COLUMNS = {
    'id': 'id',
    'project_site__name': "Площадка",
    'sub_project__name': "Проект",
    'building_number__name__name': "Здание",
    'design_chapter__short_name': "Раздел",
    'name': "Описание Задачи",
    'contractor__name': "Ответсвенный",
    'status': "Статус",
    'price': "Цена",
    'due_date': "Окончание"
}


def index(request):
    def create_filter(_df: pd.DataFrame, column_name: str, model_field_name: str):
        request_data = request.POST.getlist(model_field_name)
        return _df[column_name].isin(request_data) if \
            request_data else _df[column_name].isin(_df[column_name].unique())

    def apply_filter(_df):
        project_site__name_fiter = create_filter(_df, 'project_site__name', 'project_site')
        sub_project__name_fiter = create_filter(_df, 'sub_project__name', 'sub_project')
        status = create_filter(_df, 'status', 'status')
        contractor_choices = create_filter(_df, 'contractor__name', 'contractor')
        return _df[project_site__name_fiter & sub_project__name_fiter & contractor_choices & status]

    if request.method == 'POST':
        form = TaskFilterForm(request.POST)
    else:
        form = TaskFilterForm()
    qs = Task.objects.all().values(*FILTERED_COLUMNS.keys())
    _df = create_table_from_model(qs)
    _df = apply_filter(_df)
    df = _df.rename(FILTERED_COLUMNS, axis="columns").fillna('-').to_html(
        classes="table table-striped table-bordered",
        table_id='myTable',
        index=False,
        show_dimensions=True,
        render_links=True,
        justify='center',
        escape=False,
    )
    return render(request, 'ProjectTDL/index.html', {'df': df, 'form': form})


def e_mail_add(request):
    if request.method == 'POST':
        _form = EmailForm(request.POST)
        # if 'create_folder' in request.POST:
        if 'save_attachments' in request.POST and _form.is_valid():
            parsing_form_data = parsing_email_data_to_form(parsing_form(_form), request)
            add_form_data_to_data_base(parsing_form_data, request)
            return render(request, 'ProjectTDL/e_mail_form.html',
                          {'form': _form, 'data_path': _form.cleaned_data['link']})
    else:
        _form = EmailForm()
        return render(request, 'ProjectTDL/e_mail_form.html', {'form': _form, 'data_path': None})
