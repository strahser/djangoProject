import datetime
from pprint import pprint
from urllib.parse import urlparse
import pandas as pd
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect, HttpResponse
from django.urls import reverse_lazy
from django.views.generic import UpdateView, DeleteView
from django.contrib import messages
from pretty_html_table import pretty_html_table
from ProjectTDL.Tables import TaskTable
from ProjectTDL.forms import EmailForm, TaskFilterForm, TaskUpdateForm, TaskAdminUpdateDate, TaskAdminUpdate, \
    TaskUpdateValuesForm
from ProjectTDL.models import Task, SubTask
from ProjectTDL.querys.EmailCreate import parsing_form_for_e_mail_path, process_e_mail, add_form_data_to_data_base, \
    make_folder
from StaticData.models import ProjectSite
from services.DataFrameRender.RenderDfFromModel import renamed_dict, CloneRecord, create_df_from_model, ButtonData, \
    create_group_button, HTML_DF_PROPERTY
from django_tables2 import RequestConfig, TemplateColumn


# region Table
def create_filter_qs(request, filtered_value_list, additional_forigen_keys_list=None):
    if additional_forigen_keys_list:
        full_list = filtered_value_list + additional_forigen_keys_list
        all_object = Task.objects.select_related(*full_list)
    else:
        all_object = Task.objects.select_related(*filtered_value_list)
    res_dict = {}
    for en, data in enumerate(filtered_value_list):
        _data = request.POST.getlist(data)
        if _data:
            res_dict[f'{data}__id__in'] = _data
        else:
            res_dict[f'{data}__id__in'] = all_object.distinct().values_list(f'{data}__id', flat=True)
    qs = Task.objects.filter(**res_dict)
    return qs


def data_filter_qs(request, datefield):
    get_date = request.POST.get(datefield)
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
    df_cash_flow = create_df_from_model(Task, qs, skip_time_stamps=False) \
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

def task_action(request):
    if request.method == "POST":
        pks = request.POST.getlist("selection")
        if pks: request.session['pks'] = pks
        _form = TaskUpdateValuesForm(request.POST or None)
        if request.session.get('pks', None):
            all_fields = [f.name for f in Task._meta.fields]
            update_dict = {}
            for k, v in _form.data.items():
                if k in all_fields and v:
                    update_dict[k] = v
            if update_dict:
                try:
                    selected_objects = Task.objects.filter(pk__in=request.session.get('pks'))
                    selected_objects.update(**update_dict)
                    request.session['pks'] = None
                    for data in selected_objects:
                        messages.success(request, data)
                    return redirect('home')
                except Exception as e:
                    messages.error(request, e)
                    return redirect('home')
            else:
                _form = TaskUpdateValuesForm()
                return render(request, 'ProjectTDL/Universal_update_form.html', {'form': _form})
        else:
            messages.error(request, 'Не выбраны данные')
            return redirect('home')
    else:
        messages.error(request, 'Не выбраны данные')
        return redirect('home')


def index(request):
    filtered_value_list = ['project_site', 'sub_project', 'status', 'category', 'contractor', ]
    replaced_list = ['contractor', 'contract', 'category', 'status']
    pivot_columns_values = ['contract', 'status', 'category', ]
    pivot_columns_names = ['Договор', 'Статус', 'Категория']
    export_excluding_list = ['price', 'contract', 'owner']
    qs = create_filter_qs(request, filtered_value_list).filter(**data_filter_qs(request, 'due_date'))
    table = None
    _pivot_ui = None
    pivot_table_list = []
    gant_table = ''
    if request.method == 'POST':
        _form = TaskFilterForm(request.POST)  # fiter
        if 'submit' in request.POST and _form.is_valid():
            table = TaskTable(qs)
            RequestConfig(request).configure(table)
            for name, _column in zip(pivot_columns_names, pivot_columns_values):
                pivot_table1 = {"name": name, 'table': Task.create_pivot_table(qs, replaced_list, _column)}
                pivot_table_list.append(pivot_table1)
            # df = create_df_from_model(Task, qs)
            # _pivot_ui = pivot_ui(df, rows=['contractor'], cols=['category'],
            #                      outfile_path="templates/ProjectTDL/pivottablejs.html")

        if 'save_attachments' in request.POST and _form.is_valid():
            return TaskTable.Save_table_django(Task, qs, excluding_list=export_excluding_list)
    else:
        _form = TaskFilterForm()
        table = TaskTable(qs)
    context = {'form': _form, 'table': table, "gant_table": gant_table, 'pivot_table_list': pivot_table_list,
               'tasks': qs}
    return render(request, 'ProjectTDL/index.html', context)


def TaskCloneView(request, pk):
    queryset = Task.objects.filter(pk=pk)
    CloneRecord(queryset)
    messages.success(request, f'Запись {queryset.first().name} была скопирована ')
    return redirect("home")


def SubTaskCloneView(request, pk):
    queryset = SubTask.objects.filter(pk=pk)
    CloneRecord(queryset)
    messages.success(request, f'Запись {queryset.first().name} была скопирована ')
    previous_url = request.META.get('HTTP_REFERER')
    if previous_url and urlparse(previous_url).hostname == request.get_host():
        return HttpResponseRedirect(previous_url)


class TaskDeleteView(DeleteView):
    model = Task
    template_name = 'ProjectTDL/Delete_Form.html'

    def get_context_data(self, **kwargs):
        context = super(DeleteView, self).get_context_data(**kwargs)
        context['Name'] = "Обновление полей модели "
        if '__next__' in self.request.POST:
            context['i__next__'] = self.request.POST['__next__']
        else:
            context['i__next__'] = self.request.META['HTTP_REFERER']
        return context

    def get_success_url(self):
        self.url = self.request.POST['__next__']
        return self.url


class TaskUpdateView(UpdateView):
    model = Task
    form_class = TaskUpdateForm
    template_name = 'ProjectTDL/Update_form.html'
    success_url = reverse_lazy('home')

    def get_context_data(self, **kwargs):
        c_object = self.get_object()
        context = super(TaskUpdateView, self).get_context_data(**kwargs)
        qs = SubTask.objects.filter(parent__id=c_object.id)
        if qs:
            df_initial = create_df_from_model(SubTask, qs)
            button_data_copy = ButtonData('SubTaskCloneView', "pk", name='📄')
            button_data_delete = ButtonData('SubTaskDeleteView', "pk", cls='danger', name='X')
            button_data_update = ButtonData('SubTaskUpdateView', "pk")
            # переопределяем название задачи - добавляем ссылку на update
            df_initial['name'] = df_initial.apply(lambda x: button_data_update.create_text_link(x['id'], x['name']),
                                                  axis=1)
            button_copy = df_initial.apply(lambda x: button_data_copy.button_link(x['id']), axis=1)
            button_delete = df_initial.apply(lambda x: button_data_delete.button_link(x['id']), axis=1)
            df_initial['действия'] = create_group_button([button_copy, button_delete])
            data = df_initial.rename(renamed_dict(SubTask), axis='columns').to_html(**HTML_DF_PROPERTY)
            context['data'] = data
        return context


class SubTaskUpdateView(UpdateView):
    model = SubTask
    template_name = 'ProjectTDL/Universal_update_form.html'
    fields = '__all__'

    def get_context_data(self, **kwargs):
        context = super(UpdateView, self).get_context_data(**kwargs)
        context['Name'] = "Обновление полей модели "
        if '__next__' in self.request.POST:
            context['i__next__'] = self.request.POST['__next__']
        else:
            context['i__next__'] = self.request.META['HTTP_REFERER']
        return context

    def get_success_url(self):
        self.url = self.request.POST['__next__']
        return self.url


class SubTaskDeleteView(TaskDeleteView):
    model = SubTask
    template_name = 'ProjectTDL/Delete_Form.html'


def e_mail_add(request):
    if request.method == 'POST':
        _form = EmailForm(request.POST)
        if 'create_folder' in request.POST and _form.is_valid():
            parsing_form_for_e_mail_path(_form)
            make_folder(_form.cleaned_data['link'])
            return render(request, 'ProjectTDL/e_mail_form.html',
                          {'form': _form, 'data_path': _form.cleaned_data['link']})

        if 'save_attachments' in request.POST and _form.is_valid():
            _parsed_form = parsing_form_for_e_mail_path(_form)
            make_folder(_form.cleaned_data['link'])
            parsing_form_data = process_e_mail(_parsed_form, request)
            add_form_data_to_data_base(parsing_form_data, request)
            return render(request, 'ProjectTDL/e_mail_form.html',
                          {'form': _form, 'data_path': _form.cleaned_data['link']})
    else:
        _form = EmailForm()
        return render(request, 'ProjectTDL/e_mail_form.html', {'form': _form, 'data_path': None})
