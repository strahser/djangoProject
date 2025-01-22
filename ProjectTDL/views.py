import os
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
from adminactions.utils import flatten
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect, HttpResponse, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.decorators.http import require_POST
from django.views.generic import UpdateView, DeleteView

from AdminUtils import get_standard_display_list
from ProjectContract.models import Contractor
from ProjectTDL.StaticData import EmailType
from ProjectTDL.Tables import TaskTable, create_filter_qs, data_filter_qs, StaticFilterSettings
from ProjectTDL.admin import TaskAdmin
from ProjectTDL.forms import TaskUpdateValuesForm, TaskFilterForm, TaskUpdateForm, EmailForm, EmailFilterForm
from ProjectTDL.models import Task, SubTask, Email
from ProjectTDL.querys.OutlookEmailCreate import parsing_form_for_e_mail_path, process_e_mail, add_form_data_to_data_base, \
    make_folder
from ProjectTDL.ЕmailParser.ParsingImapEmailToDB import ParsingImapEmailToDB
from StaticData.models import Status
from services.DataFrameRender.RenderDfFromModel import renamed_dict, CloneRecord, create_df_from_model, ButtonData, \
    create_group_button, HTML_DF_PROPERTY, create_pivot_table
from django_tables2 import RequestConfig, TemplateColumn
from django.views import View
from django.contrib import admin, messages

from services.Downloads.ExcelDownload import df_to_excel_in_memory


def handle_incoming_email(request):
    # url_redirect = reverse('admin/ProjectTDL/email/')
    if request.method == 'POST':
        email_limit = int(request.POST.get('mail_count'))
        initial_folder_list = {'INBOX': EmailType.IN.name,
                               'Отправленные': EmailType.OUT.name
                               }
        actions_list = []
        scip_list = []
        directory = os.path.join('e:\Проекты Симрус', 'Переписка', 'imap_attachments')
        for folder, folder_db_name in initial_folder_list.items():
            root_path = os.path.join(directory, folder)
            _parser = ParsingImapEmailToDB(root_path)
            _parser.main(folder_db_name, folder, limit=email_limit)
            actions_list.append(_parser.create_action_list)
            scip_list.append(_parser.skip_action_list)
        actions_list = flatten(actions_list)
        scip_list = flatten(scip_list)
        if actions_list:
            res_list = [str(val) for val in actions_list]
            messages.success(request, f"Почта сохранена Для следующих позиций {res_list}")
        else:
            res_list = [str(val) for val in scip_list]
            messages.info(request, f"Нечего обновлять")
        return redirect('admin:ProjectTDL_email_changelist')
    else:
        messages.error(request, "Возникли ошибки")
        return redirect('admin:ProjectTDL_email_changelist')


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


class SelectEmailView(View):
    def get(self, request, task_id):
        senders_list = Email.objects.values_list('sender', flat=True)
        senders = sorted(set(sender for sender in senders_list if sender))
        sender_choices = [(sender, sender) for sender in senders]
        form = EmailFilterForm(request.GET, sender_choices=sender_choices)
        emails = Email.objects.all()
        task = Task.objects.get(pk=task_id)

        if form.is_valid():
            project_site = form.cleaned_data.get('project_site')
            contractor = form.cleaned_data.get('contractor')
            email_type = form.cleaned_data.get('email_type')
            search_query = form.cleaned_data.get('search_query')
            senders = form.cleaned_data.get('sender_choices')

            if project_site:
                emails = emails.filter(project_site=project_site)
            if contractor:
                emails = emails.filter(contractor=contractor)
            if email_type:
                emails = emails.filter(email_type=email_type)
            if senders:
                emails = emails.filter(sender__in=senders)
            if search_query:
                emails = emails.filter(
                    Q(name__icontains=search_query) |
                    Q(subject__icontains=search_query) |
                    Q(sender__icontains=search_query) |
                    Q(receiver__icontains=search_query)
                )

        return render(request, 'ProjectTDL/select_email.html', {
            'form': form,
            'emails': emails,
            'task': task,
        })

    def post(self, request, task_id):
        selected_email_ids = request.POST.getlist('selected_emails')
        task = Task.objects.get(pk=task_id)
        emails = Email.objects.filter(id__in=selected_email_ids)
        if 'edit_action' in request.POST:
           edit_url = reverse('edit_email_form')
           return redirect(f'{edit_url}?selected_emails={",".join(selected_email_ids)}&task_id={task_id}')
        else:
            for email in emails:
                email.parent = task
                email.save()
            return redirect('admin:ProjectTDL_task_change', task_id)


class EditEmailFormView(View):
    def get(self, request):
       selected_email_ids = request.GET.get('selected_emails', '').split(',')
       selected_email_ids = [email_id.replace(u'\xa0', '') for email_id in selected_email_ids if email_id]
       task_id = request.GET.get('task_id')
       if not selected_email_ids:
            return redirect('select_email', task_id=task_id)
       emails = Email.objects.filter(id__in=selected_email_ids)
       senders_list = Email.objects.values_list('sender', flat=True)
       senders = sorted(set(sender for sender in senders_list if sender))
       sender_choices = [(sender, sender) for sender in senders]
       form = EmailFilterForm(request.GET, sender_choices=sender_choices)
       return render(request, 'ProjectTDL/edit_email_form.html', {
          'emails': emails,
           'form':form,
           'task_id': task_id,
            'senders': senders,
         })
    def post(self, request):
        selected_email_ids = request.POST.getlist('selected_emails')
        selected_email_ids = [email_id.replace(u'\xa0', '') for email_id in selected_email_ids]
        task_id=request.POST.get('task_id')
        if selected_email_ids:
            emails = Email.objects.filter(id__in=selected_email_ids)
            if request.POST:
                update_data = {}
                for key, value in request.POST.items():
                    if key.endswith('_checkbox') and value == 'True':
                        field_name = key.replace('_checkbox', '')
                        update_data[field_name] = request.POST.get(field_name)

                if update_data:
                    emails.update(**update_data)
            if emails:
                if emails.first().parent:
                    return redirect('select_email', task_id=emails.first().parent.id)
        return redirect('select_email', task_id=task_id)

