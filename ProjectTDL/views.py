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
from ProjectTDL.Tables import TaskNodeTable, create_filter_qs, data_filter_qs, StaticFilterSettings
from ProjectTDL.forms import TaskUpdateValuesForm, TaskFilterForm, TaskUpdateForm, TaskNodeQuickForm
from ProjectTDL.models import TaskNode
from ProjectTDL.reports import ReportGenerator
from StaticData.models import Status, Category, ProjectSite, SubProject, BuildingNumber
from services.DataFrameRender.RenderDfFromModel import renamed_dict, CloneRecord, create_df_from_model, ButtonData, \
    create_group_button, HTML_DF_PROPERTY, create_pivot_table


def task_action(request):
    if request.method == "POST":
        pks = request.POST.getlist("selection")
        if pks: request.session['pks'] = pks
        _form = TaskUpdateValuesForm(request.POST or None)
        if request.session.get('pks', None):
            all_fields = [f.name for f in TaskNode._meta.fields]
            update_dict = {}
            for k, v in _form.data.items():
                if k in all_fields and v:
                    update_dict[k] = v
            if update_dict:
                try:
                    selected_objects = TaskNode.objects.filter(pk__in=request.session.get('pks'))
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
    qs = TaskNode.objects.filter(node_type='task').select_related(*StaticFilterSettings.filtered_value_list)

    filter_dict = create_filter_qs(request, StaticFilterSettings.filtered_value_list)
    qs = qs.filter(**filter_dict)
    qs = qs.filter(**data_filter_qs(request, 'due_date'))

    _form = TaskFilterForm(request.POST or None)
    table = TaskNodeTable(qs)
    RequestConfig(request).configure(table)

    tree_roots = TaskNode.objects.filter(parent__isnull=True, node_type='task').select_related(
        'project_site', 'status', 'contractor'
    ).prefetch_related('children')

    pivot_table_list = []
    gant_table = ''
    if request.method == 'POST':

        if 'submit' in request.POST and _form.is_valid():
            for name, _column in zip(StaticFilterSettings.pivot_columns_names,
                                     StaticFilterSettings.pivot_columns_values):
                pivot_table1 = {"name": name,
                                'table': create_pivot_table(TaskNode, qs, StaticFilterSettings.replaced_list, _column)}
                pivot_table_list.append(pivot_table1)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(request, 'ProjectTDL/custom_table_view.html', {'table': table, 'form': _form})

        if 'save_attachments' in request.POST and _form.is_valid():
            df_initial = create_df_from_model(TaskNode, qs)
            df_initial['project_site'] = df_initial['project_site'].apply(lambda x: getattr(x, 'name'))
            df_initial = df_initial.sort_values('project_site')
            df_export = df_initial \
                .filter(get_standard_display_list(TaskNode, excluding_list=StaticFilterSettings.export_excluding_list)) \
                .rename(renamed_dict(TaskNode), axis='columns') \
                .fillna('')
            messages.success(request, f"успешно экспортировано {df_export.shape[0]} строк {df_export.shape[1]} столбцов")
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
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

    context = {
        'form': _form,
        'table': table,
        "gant_table": gant_table,
        'pivot_table_list': pivot_table_list,
        'tasks': qs,
        'tree_roots': tree_roots,
        'all_contractors': Contractor.objects.all().order_by('name'),
        'all_statuses': Status.objects.all().order_by('name'),
        'all_categories': Category.objects.all().order_by('name'),
        'all_project_sites': ProjectSite.objects.all().order_by('name'),
        'all_sub_projects': SubProject.objects.all().order_by('name'),
    }
    return render(request, 'ProjectTDL/custom_task_view_enhanced.html', context)


def TaskCloneView(request, pk):
    queryset = TaskNode.objects.filter(pk=pk)
    CloneRecord(queryset)
    messages.success(request, f'Запись {queryset.first().name} была скопирована ')
    return redirect("custom_task_view")


def SubTaskCloneView(request, pk):
    queryset = TaskNode.objects.filter(pk=pk)
    CloneRecord(queryset)
    messages.success(request, f'Запись {queryset.first().name} была скопирована ')
    previous_url = request.META.get('HTTP_REFERER')
    if previous_url and urlparse(previous_url).hostname == request.get_host():
        return HttpResponseRedirect(previous_url)


class TaskDeleteView(DeleteView):
    model = TaskNode
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
    model = TaskNode
    form_class = TaskUpdateForm
    template_name = 'ProjectTDL/Update_form.html'
    success_url = reverse_lazy('home')

    def get_context_data(self, **kwargs):
        c_object = self.get_object()
        context = super(TaskUpdateView, self).get_context_data(**kwargs)
        qs = c_object.get_children().filter(node_type='subtask')
        if qs:
            df_initial = create_df_from_model(qs.model, qs)
            button_data_copy = ButtonData('SubTaskCloneView', "pk", name='📄')
            button_data_delete = ButtonData('SubTaskDeleteView', "pk", cls='danger', name='X')
            button_data_update = ButtonData('SubTaskUpdateView', "pk")
            df_initial['name'] = df_initial.apply(lambda x: button_data_update.create_text_link(x['id'], x['name']),
                                                  axis=1)
            button_copy = df_initial.apply(lambda x: button_data_copy.button_link(x['id']), axis=1)
            button_delete = df_initial.apply(lambda x: button_data_delete.button_link(x['id']), axis=1)
            df_initial['действия'] = create_group_button([button_copy, button_delete])
            data = df_initial.rename(renamed_dict(TaskNode), axis='columns').to_html(**HTML_DF_PROPERTY)
            context['data'] = data
        return context
@require_POST
def update_task_field(request):
    try:
        task_id = int(request.POST.get('task_id'))
        field = request.POST.get('field')
        value = request.POST.get('value')

        task = get_object_or_404(TaskNode, pk=task_id)

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

def manage_reference(request):
    model_map = {
        'project_site': ProjectSite,
        'sub_project': SubProject,
        'status': Status,
        'category': Category,
        'contractor': Contractor,
    }
    model_key = request.POST.get('model') or request.GET.get('model')
    Model = model_map.get(model_key)
    if not Model:
        return JsonResponse({'status': 'error', 'message': 'Unknown model'})

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            name = request.POST.get('name', '').strip()
            if name:
                obj, created = Model.objects.get_or_create(name=name)
                if created:
                    return JsonResponse({'status': 'ok', 'object': {'pk': obj.pk, 'name': obj.name}})
                return JsonResponse({'status': 'error', 'message': 'Уже существует'})
            return JsonResponse({'status': 'error', 'message': 'Укажите название'})
        elif action == 'delete':
            obj_id = request.POST.get('id')
            try:
                Model.objects.filter(pk=obj_id).delete()
                return JsonResponse({'status': 'ok'})
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': str(e)})

    objects = Model.objects.all().order_by('name')
    return JsonResponse({
        'objects': [{'pk': o.pk, 'name': o.name} for o in objects]
    })


@require_POST
def quick_create_task(request):
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'status': 'error', 'message': 'Укажите название задачи'})

    task = TaskNode.objects.create(
        name=name,
        node_type='task',
        project_site_id=request.POST.get('project_site') or None,
        sub_project_id=request.POST.get('sub_project') or None,
        status_id=request.POST.get('status') or None,
        category_id=request.POST.get('category') or None,
        contractor_id=request.POST.get('contractor') or None,
    )
    return JsonResponse({'status': 'ok', 'task_id': task.pk, 'task_name': task.name})


def cascade_filter_options(request):
    from StaticData.models import Status, Category, SubProject
    from ProjectContract.models import Contractor
    project_site_id = request.GET.get('project_site')
    if not project_site_id:
        return JsonResponse({
            'sub_projects': [{'pk': s.pk, 'name': s.name} for s in SubProject.objects.all().order_by('name')],
            'statuses': [{'pk': s.pk, 'name': s.name} for s in Status.objects.all().order_by('name')],
            'categories': [{'pk': c.pk, 'name': c.name} for c in Category.objects.all().order_by('name')],
            'contractors': [{'pk': c.pk, 'name': c.name} for c in Contractor.objects.all().order_by('name')],
        })

    def _all_entries():
        return {
            'sub_projects': [{'pk': s.pk, 'name': s.name} for s in SubProject.objects.all().order_by('name')],
            'statuses': [{'pk': s.pk, 'name': s.name} for s in Status.objects.all().order_by('name')],
            'categories': [{'pk': c.pk, 'name': c.name} for c in Category.objects.all().order_by('name')],
            'contractors': [{'pk': c.pk, 'name': c.name} for c in Contractor.objects.all().order_by('name')],
        }

    qs = TaskNode.objects.filter(node_type='task', project_site_id=project_site_id)
    from django.db.models import Count

    def _field_items(field_name, related_name, model_class):
        vals = list(qs.filter(**{field_name + '__isnull': False}).order_by(related_name + '__name').values_list(field_name + '_id', flat=True).distinct())
        if vals:
            return [{'pk': obj.pk, 'name': obj.name} for obj in model_class.objects.filter(pk__in=vals).order_by('name')]
        return [{'pk': obj.pk, 'name': obj.name} for obj in model_class.objects.all().order_by('name')]

    return JsonResponse({
        'sub_projects': _field_items('sub_project', 'sub_project', SubProject),
        'statuses': _field_items('status', 'status', Status),
        'categories': _field_items('category', 'category', Category),
        'contractors': _field_items('contractor', 'contractor', Contractor),
    })


@require_POST
def quick_create_subtask(request):
    parent_id = request.POST.get('parent_id')
    name = request.POST.get('name', '').strip()
    if not parent_id or not name:
        return JsonResponse({'status': 'error', 'message': 'Укажите родительскую задачу и название'})
    try:
        parent = TaskNode.objects.get(pk=parent_id)
        subtask = TaskNode.objects.create(
            name=name,
            node_type='subtask',
            parent=parent,
            project_site=parent.project_site,
            sub_project=parent.sub_project,
            status=parent.status,
            category=parent.category,
            contractor=parent.contractor,
        )
        return JsonResponse({'status': 'ok', 'subtask_id': subtask.pk, 'subtask_name': subtask.name})
    except TaskNode.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Родительская задача не найдена'})


@require_POST
def bulk_update_tasks(request):
    task_ids = request.POST.getlist('task_ids')
    if not task_ids:
        return JsonResponse({'status': 'error', 'message': 'Задачи не выбраны'})

    updates = {}
    field_mapping = {
        'project_site': 'project_site_id',
        'sub_project': 'sub_project_id',
        'status': 'status_id',
        'category': 'category_id',
        'contractor': 'contractor_id',
        'due_date': 'due_date',
        'price': 'price',
    }

    for field, db_field in field_mapping.items():
        value = request.POST.get(field)
        if value:
            if field in ['status', 'category', 'contractor']:
                try:
                    updates[db_field] = int(value)
                except ValueError:
                    pass
            elif field == 'price':
                try:
                    updates[db_field] = float(value.replace(',', '.'))
                except ValueError:
                    pass
            else:
                updates[db_field] = value

    if updates:
        updated_count = TaskNode.objects.filter(id__in=task_ids).update(**updates)
        return JsonResponse({
            'status': 'ok',
            'message': f'Успешно обновлено {updated_count} задач',
            'updated_fields': list(updates.keys())
        })

    return JsonResponse({'status': 'error', 'message': 'Нет данных для обновления'})


@require_POST
def save_user_settings(request):
    return JsonResponse({'status': 'ok'})


def filter_tasks_ajax(request):
    from django.template.loader import render_to_string
    qs = TaskNode.objects.filter(node_type='task').select_related(*StaticFilterSettings.filtered_value_list)

    project_site = request.GET.get('project_site')
    sub_project = request.GET.get('sub_project')
    status_id = request.GET.get('status')
    category_id = request.GET.get('category')
    contractor_id = request.GET.get('contractor')
    due_date = request.GET.get('due_date')

    if project_site:
        qs = qs.filter(project_site_id=project_site)
    if sub_project:
        qs = qs.filter(sub_project_id=sub_project)
    if status_id:
        qs = qs.filter(status_id=status_id)
    if category_id:
        qs = qs.filter(category_id=category_id)
    if contractor_id:
        qs = qs.filter(contractor_id=contractor_id)
    if due_date:
        filter_dict = data_filter_qs(request, 'due_date')
        qs = qs.filter(**filter_dict)

    table = TaskNodeTable(qs)
    RequestConfig(request).configure(table)
    table_html = render_to_string('django_tables2/bootstrap_no_pag.html', {'table': table}, request)

    tree_roots = TaskNode.objects.filter(parent__isnull=True, node_type='task').select_related(
        'project_site', 'status', 'contractor'
    ).prefetch_related('children')
    tree_html = render_to_string('ProjectTDL/task_tree_nodes_partial.html', {'tree_roots': tree_roots}, request)

    return JsonResponse({
        'table': table_html,
        'tree': tree_html,
        'count': qs.count(),
    })


@login_required
def list_pinned_projects(request):
    from .models import ProjectPin
    pins = ProjectPin.objects.filter(user=request.user).select_related('project_site')
    return JsonResponse([
        {'id': p.project_site_id, 'name': p.project_site.name}
        for p in pins
    ], safe=False)


@login_required
@require_POST
def add_pinned_project(request):
    from .models import ProjectPin
    from StaticData.models import ProjectSite
    site_id = request.POST.get('project_site_id')
    if not site_id:
        return JsonResponse({'error': 'project_site_id required'}, status=400)
    site = get_object_or_404(ProjectSite, pk=site_id)
    ProjectPin.objects.get_or_create(user=request.user, project_site=site)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def remove_pinned_project(request):
    from .models import ProjectPin
    site_id = request.POST.get('project_site_id')
    if not site_id:
        return JsonResponse({'error': 'project_site_id required'}, status=400)
    ProjectPin.objects.filter(user=request.user, project_site_id=site_id).delete()
    return JsonResponse({'ok': True})


class SubTaskUpdateView(UpdateView):
    model = TaskNode
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
    template_name = 'ProjectTDL/Delete_Form.html'


@login_required
def task_detail(request, pk):
    """Рабочая карточка задачи: удобнее админки — письма, подзадачи в одном месте."""
    task = get_object_or_404(
        TaskNode.objects.select_related(
            'project_site', 'sub_project', 'building_number__name', 'design_chapter',
            'contractor', 'status', 'category', 'contract', 'owner'
        ),
        pk=pk
    )

    linked_emails = task.emails.select_related(
        'project_site', 'contractor'
    ).prefetch_related('attachments', 'email_tags__tag').order_by('-email_stamp')[:100]

    subtasks = task.get_children().filter(node_type='subtask').order_by('id')

    subtask_form = TaskNodeQuickForm(request.POST or None, prefix='subtask')
    if request.method == 'POST' and 'create_subtask' in request.POST:
        if subtask_form.is_valid():
            st = subtask_form.save(commit=False)
            st.node_type = 'subtask'
            st.parent = task
            st.owner = request.user
            st.project_site = task.project_site
            st.sub_project = task.sub_project
            st.save()
            messages.success(request, f'Подзадача «{st.name}» добавлена')
            return redirect('task_detail', pk=pk)

    from ProjectTDL.models import TaskDueDateHistory
    from StaticData.models import Status as TaskStatus
    context = {
        'task': task,
        'subtasks': subtasks,
        'linked_emails': linked_emails,
        'history': TaskDueDateHistory.objects.filter(task_node_id=pk).select_related('changed_by'),
        'subtask_form': subtask_form,
        'all_statuses': TaskStatus.objects.all().order_by('name'),
        'subtask_total': task.subtree_price,
    }
    return render(request, 'ProjectTDL/task_detail.html', context)


@login_required
def task_tree_view(request):
    """MPTT tree view — все задачи и подзадачи в виде дерева."""
    roots = TaskNode.objects.filter(parent__isnull=True).select_related(
        'project_site', 'sub_project', 'status', 'contractor'
    ).prefetch_related('children')
    context = {'roots': roots}
    return render(request, 'ProjectTDL/task_tree.html', context)


@login_required
def generate_custom_report(request):
    """View для генерации кастомного отчета"""
    task_ids = request.GET.getlist('task_ids')

    if not task_ids:
        return HttpResponse("Не выбраны задачи для отчета")

    tasks = TaskNode.objects.filter(id__in=task_ids).select_related(
        'project_site', 'sub_project', 'building_number__name',
        'design_chapter', 'contractor', 'status', 'category', 'contract'
    ).prefetch_related('due_date_history')

    html_report = ReportGenerator.generate_html_report(tasks)

    response = HttpResponse(html_report, content_type='text/html')
    response['Content-Disposition'] = 'inline; filename="custom_tasks_report.html"'

    return response









