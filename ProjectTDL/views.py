from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect, HttpResponse, get_object_or_404
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import UpdateView, DeleteView
from django_tables2 import RequestConfig

from AdminUtils import get_standard_display_list
from ProjectContract.models import Contractor
from ProjectTDL.Tables import TaskTable, create_filter_qs, data_filter_qs, StaticFilterSettings
from ProjectTDL.forms import TaskUpdateValuesForm, TaskFilterForm, TaskUpdateForm
from ProjectTDL.models import Task, SubTask
from ProjectTDL.reports import ReportGenerator
from StaticData.models import Status
from services.DataFrameRender.RenderDfFromModel import renamed_dict, CloneRecord, create_df_from_model, ButtonData, \
    create_group_button, HTML_DF_PROPERTY, create_pivot_table


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


def custom_task_view(request):
    # получаем все объекты
    qs = Task.objects.all().select_related(*StaticFilterSettings.filtered_value_list)

    # получаем фильтры из запроса
    filter_dict = create_filter_qs(request, StaticFilterSettings.filtered_value_list)

    # применяем фильтры
    qs = qs.filter(**filter_dict)

    # применяем фильтр по дате
    qs = qs.filter(**data_filter_qs(request, 'due_date'))


    _form = TaskFilterForm(request.POST or None)  # Инициализация формы сразу

    table = TaskTable(qs)
    RequestConfig(request).configure(table)


    pivot_table_list = []
    gant_table = ''
    if request.method == 'POST':

        if 'submit' in request.POST and _form.is_valid():
            for name, _column in zip(StaticFilterSettings.pivot_columns_names,
                                     StaticFilterSettings.pivot_columns_values):
                pivot_table1 = {"name": name,
                                'table': create_pivot_table(Task, qs, StaticFilterSettings.replaced_list, _column)}
                pivot_table_list.append(pivot_table1)


        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':  # проверка, что запрос AJAX
            return render(request, 'ProjectTDL/custom_table_view.html', {'table': table,  'form': _form})

        if 'save_attachments' in request.POST and _form.is_valid():
            # export_table = TaskTable.Save_table_django(Task, qs, excluding_list=StaticFilterSettings.export_excluding_list)
            df_initial = create_df_from_model(Task, qs)
            df_initial['project_site'] = df_initial['project_site'].apply(lambda x: getattr(x, 'name'))
            df_initial = df_initial.sort_values('project_site')
            df_export = df_initial \
                .filter(get_standard_display_list(Task, excluding_list=StaticFilterSettings.export_excluding_list)) \
                .rename(renamed_dict(Task), axis='columns') \
                .fillna('')
            # Создаем HTTP-ответ с Excel-файлом
            messages.success(request, f"успешно экспортировано {df_export.shape[0]} строк {df_export.shape[1]} столбцов")
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = 'attachment; filename="Задачи.xlsx"'
            writer = pd.ExcelWriter(response, engine='xlsxwriter')
            df_export.to_excel(writer, sheet_name='Задачи', index=False, freeze_panes=(1, 1))
            workbook = writer.book
            worksheet = writer.sheets['Задачи']
            column_settings = [{'header': column}  for column in df_export]
            (max_row, max_col) = df_export.shape
            worksheet.add_table(0, 0, max_row, max_col - 1,
                           {'columns': column_settings,
                            'banded_columns': True,
                            'name': 'Задачи',
                            'autofilter': True,
                            'style': 'Table Style Light 8'})
            writer.close()
            return response


    context = {'form': _form, 'table': table, "gant_table": gant_table, 'pivot_table_list': pivot_table_list,
               'tasks': qs}
    return render(request, 'ProjectTDL/custom_table_view.html', context)


def TaskCloneView(request, pk):
    queryset = Task.objects.filter(pk=pk)
    CloneRecord(queryset)
    messages.success(request, f'Запись {queryset.first().name} была скопирована ')
    return redirect("custom_task_view")


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
@require_POST
def update_task_field(request):
    try:
        task_id = int(request.POST.get('task_id'))
        field = request.POST.get('field')
        value = request.POST.get('value')

        task = get_object_or_404(Task, pk=task_id)

        if field == 'contractor':
            contractor = get_object_or_404(Contractor, pk=value)
            task.contractor = contractor
        elif field == 'status':
            status = get_object_or_404(Status, pk=value)
            task.status = status
        elif field == 'due_date':
            if value:
                task.due_date = datetime.strptime(value, '%Y-%m-%d').date()
            else:
                task.due_date = None
        elif field == 'price':
            if value:
                task.price = float(value)
            else:
                task.price = None
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid field'})

        task.save()
        return JsonResponse({'status': 'ok', 'message': f'{field} updated'})
    except (ValueError, KeyError, Status.DoesNotExist, Contractor.DoesNotExist, Exception) as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

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


@login_required
def generate_custom_report(request):
    """View для генерации кастомного отчета"""
    task_ids = request.GET.getlist('task_ids')

    if not task_ids:
        return HttpResponse("Не выбраны задачи для отчета")

    # Получаем задачи
    tasks = Task.objects.filter(id__in=task_ids).select_related(
        'project_site', 'sub_project', 'building_number__name',
        'design_chapter', 'contractor', 'status', 'category', 'contract'
    ).prefetch_related('subtask_set', 'due_date_history')

    # Генерируем отчет
    html_report = ReportGenerator.generate_html_report(tasks)

    response = HttpResponse(html_report, content_type='text/html')
    response['Content-Disposition'] = 'inline; filename="custom_tasks_report.html"'

    return response









