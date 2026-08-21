from datetime import datetime
import json
from urllib.parse import urlparse

import pandas as pd
from django.contrib import messages
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect, HttpResponse, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import UpdateView, DeleteView
from django_tables2 import RequestConfig

from AdminUtils import get_standard_display_list
from ProjectContract.models import Contractor
from ProjectTDL.Tables import TaskNodeTable, create_filter_qs, data_filter_qs, StaticFilterSettings
from ProjectTDL.forms import TaskUpdateValuesForm, TaskFilterForm, TaskUpdateForm, TaskNodeQuickForm
from ProjectTDL.models import TaskNode, UserSettings, TaskFilterState
from ProjectTDL.reports import ReportGenerator
from StaticData.models import Status, Category, ProjectSite, BuildingNumber, BuildingType, DesignChapter
from services.DataFrameRender.RenderDfFromModel import renamed_dict, CloneRecord, create_df_from_model, ButtonData, \
    create_group_button, HTML_DF_PROPERTY, create_pivot_table


FILTER_FIELDS = ('project_site', 'building_number', 'status', 'category', 'contractor', 'due_date')


def get_filter_state_for_request(request):
    """Состояние фильтров для текущего пользователя: по активному проекту, иначе общее."""
    if not request.user.is_authenticated:
        return None
    settings = UserSettings.objects.filter(user=request.user).first()
    active_project_id = settings.active_project_id if settings else None
    if active_project_id:
        state = TaskFilterState.objects.filter(user=request.user, project_site_id=active_project_id).first()
        if state:
            return state
    return TaskFilterState.objects.filter(user=request.user, project_site__isnull=True).first()


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
                    return redirect('custom_task_view')
                except Exception as e:
                    messages.error(request, e)
                    return redirect('custom_task_view')
            else:
                _form = TaskUpdateValuesForm()
                return render(request, 'ProjectTDL/Universal_update_form.html', {'form': _form})
        else:
            messages.error(request, 'Не выбраны данные')
            return redirect('custom_task_view')
    else:
        messages.error(request, 'Не выбраны данные')
        return redirect('custom_task_view')


def _task_subtree_qs(filter_dict, date_filter):
    """Задачи, подходящие под фильтр, и все их подзадачи (поддеревья по MPTT).

    Подзадачи наследуют не все поля от родителя, поэтому их нельзя фильтровать
    напрямую — иначе подзадачи с пустыми полями (например, без ответственного)
    пропадут и из плоского списка, и из дерева.
    """
    tasks_qs = TaskNode.objects.filter(node_type='task')
    if filter_dict:
        tasks_qs = tasks_qs.filter(**filter_dict)
    if date_filter:
        tasks_qs = tasks_qs.filter(**date_filter)

    bounds = Q()
    for task in tasks_qs.only('tree_id', 'lft', 'rght'):
        bounds |= Q(tree_id=task.tree_id, lft__gte=task.lft, lft__lte=task.rght)
    if not bounds:
        return TaskNode.objects.none()
    return TaskNode.objects.filter(bounds).select_related(
        *StaticFilterSettings.filtered_value_list
    ).order_by('tree_id', 'lft')


def custom_task_view(request):
    initial = {}
    filter_state = None
    if request.method == 'GET':
        filter_state = get_filter_state_for_request(request)
        if filter_state:
            initial = {k: v for k, v in (filter_state.params or {}).items() if v}

    filter_dict = create_filter_qs(request, StaticFilterSettings.filtered_value_list)
    if not filter_dict and initial:
        filter_dict = create_filter_qs(request, StaticFilterSettings.filtered_value_list, data=initial)
    date_filter = data_filter_qs(request, 'due_date', data=initial if not request.POST else None)
    qs = _task_subtree_qs(filter_dict, date_filter)

    _form = TaskFilterForm(request.POST or None, initial=initial)
    table = TaskNodeTable(qs)
    table.view_mode = 'tree'
    RequestConfig(request, paginate=False).configure(table)

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

    user_settings = {
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
        'auto_save': True,
        'active_project_id': '',
    }
    if request.user.is_authenticated:
        _us = UserSettings.objects.filter(user=request.user).first()
        if _us:
            user_settings = {
                'inherit_props': _us.inherit_props,
                'new_task_position': _us.new_task_position,
                'default_tree_view': _us.default_tree_view,
                'default_project_site': _us.default_project_site,
                'default_building': _us.default_building,
                'default_category': _us.default_category,
                'default_status': _us.default_status,
                'default_contractor': _us.default_contractor,
                'column_visibility': _us.column_visibility or {},
                'column_widths': _us.column_widths or {},
                'column_order': _us.column_order or [],
                'panel_fields': _us.panel_fields or {},
                'page_length': _us.page_length,
                'auto_save': _us.auto_save,
                'active_project_id': _us.active_project_id or '',
            }

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
        'all_buildings': BuildingNumber.objects.all().order_by('building_number'),
        'all_building_types': BuildingType.objects.all().order_by('name'),
        'all_design_chapters': DesignChapter.objects.all().order_by('short_name'),
        'user_settings': user_settings,
        'filter_state': (filter_state.params or {}) if filter_state else {},
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
        next_url = (
            self.request.POST.get('__next__')
            or self.request.GET.get('next')
            or self.request.META.get('HTTP_REFERER')
            or reverse('custom_task_view')
        )
        context['i__next__'] = next_url
        return context

    def get_success_url(self):
        return self.request.POST.get('__next__') or reverse('custom_task_view')


class TaskUpdateView(UpdateView):
    model = TaskNode
    form_class = TaskUpdateForm
    template_name = 'ProjectTDL/Update_form.html'
    success_url = reverse_lazy('custom_task_view')

    def get_context_data(self, **kwargs):
        c_object = self.get_object()
        context = super(TaskUpdateView, self).get_context_data(**kwargs)
        context['i__next__'] = self.request.POST.get('__next__') or reverse('custom_task_view')
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
        elif field == 'category':
            category = get_object_or_404(Category, pk=value)
            task.category = category
        elif field == 'design_chapter':
            design_chapter = get_object_or_404(DesignChapter, pk=value)
            task.design_chapter = design_chapter
        elif field == 'building_number':
            building_number = get_object_or_404(BuildingNumber, pk=value)
            task.building_number = building_number
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
    except (ValueError, KeyError, Status.DoesNotExist, Category.DoesNotExist,
            Contractor.DoesNotExist, DesignChapter.DoesNotExist, BuildingNumber.DoesNotExist, Exception) as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

def manage_reference(request):
    model_map = {
        'project_site': ProjectSite,
        'status': Status,
        'category': Category,
        'contractor': Contractor,
        'design_chapter': DesignChapter,
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
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Требуется авторизация'})

    project_site = request.POST.get('project_site') or None
    status = request.POST.get('status') or None
    category = request.POST.get('category') or None
    contractor = request.POST.get('contractor') or None
    building_number = request.POST.get('building_number') or None

    # Наследование контекста от ПОСЛЕДНЕЙ задачи выбранного проекта:
    # если у пользователя включено наследование (inherit_props) или любой default_*,
    # незаполненные поля берутся из последней задачи проекта (order_by -pk).
    settings = None
    if request.user.is_authenticated:
        settings = UserSettings.objects.filter(user=request.user).first()
    inherit = bool(settings and (
        settings.inherit_props
        or settings.default_project_site
        or settings.default_building
        or settings.default_category
        or settings.default_status
        or settings.default_contractor
    ))
    if inherit and project_site:
        last_task = TaskNode.objects.filter(
            node_type='task', project_site_id=project_site
        ).order_by('-pk').first()
        if last_task:
            if not status:
                status = last_task.status_id or None
            if not category:
                category = last_task.category_id or None
            if not contractor:
                contractor = last_task.contractor_id or None
            if not building_number:
                building_number = last_task.building_number_id or None

    task = TaskNode.objects.create(
        name=name,
        node_type='task',
        owner=request.user,
        project_site_id=project_site,
        status_id=status,
        category_id=category,
        contractor_id=contractor,
        building_number_id=building_number,
    )
    return JsonResponse({'status': 'ok', 'task_id': task.pk, 'task_name': task.name})


def cascade_filter_options(request):
    from StaticData.models import Status, Category
    from ProjectContract.models import Contractor
    project_site_id = request.GET.get('project_site')
    building_type_id = request.GET.get('building_number')  # id BuildingType (тип здания)

    def _all_entries():
        return {
            'statuses': [{'pk': s.pk, 'name': s.name} for s in Status.objects.all().order_by('name')],
            'categories': [{'pk': c.pk, 'name': c.name} for c in Category.objects.all().order_by('name')],
            'contractors': [{'pk': c.pk, 'name': c.name} for c in Contractor.objects.all().order_by('name')],
            'buildings': [{'pk': b.pk, 'name': b.name} for b in BuildingType.objects.all().order_by('name')],
        }

    if not project_site_id and not building_type_id:
        return JsonResponse(_all_entries())

    qs = TaskNode.objects.filter(node_type='task')
    if project_site_id:
        qs = qs.filter(project_site_id=project_site_id)
    if building_type_id:
        qs = qs.filter(building_number__name_id=building_type_id)

    def _field_items(field_name, related_name, model_class):
        vals = list(qs.filter(**{field_name + '__isnull': False}).order_by(related_name + '__name').values_list(field_name + '_id', flat=True).distinct())
        if vals:
            return [{'pk': obj.pk, 'name': obj.name} for obj in model_class.objects.filter(pk__in=vals).order_by('name')]
        return [{'pk': obj.pk, 'name': obj.name} for obj in model_class.objects.all().order_by('name')]

    def _building_items():
        # Типы зданий каскадируются от ПРОЕКТА (не от выбранного типа): список сохраняет выбранное значение.
        bqs = TaskNode.objects.filter(node_type='task')
        if project_site_id:
            bqs = bqs.filter(project_site_id=project_site_id)
        vals = list(bqs.filter(building_number__isnull=False, building_number__name__isnull=False)
                    .values_list('building_number__name_id', flat=True).distinct())
        if vals:
            return [{'pk': obj.pk, 'name': obj.name}
                    for obj in BuildingType.objects.filter(pk__in=vals).order_by('name')]
        return [{'pk': obj.pk, 'name': obj.name}
                for obj in BuildingType.objects.all().order_by('name')]

    return JsonResponse({
        'statuses': _field_items('status', 'status', Status),
        'categories': _field_items('category', 'category', Category),
        'contractors': _field_items('contractor', 'contractor', Contractor),
        'buildings': _building_items(),
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
            owner=request.user if request.user.is_authenticated else None,
            project_site=parent.project_site,
            status=parent.status,
            category=parent.category,
            contractor=parent.contractor,
            building_number=parent.building_number,
            design_chapter=parent.design_chapter,
        )
        return JsonResponse({'status': 'ok', 'subtask_id': subtask.pk, 'subtask_name': subtask.name})
    except TaskNode.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Родительская задача не найдена'})


@require_POST
def bulk_delete_tasks(request):
    task_ids = request.POST.getlist('task_ids')
    task_ids = [t for ids in task_ids for t in ids.split(',') if t]
    if not task_ids:
        return JsonResponse({'status': 'error', 'message': 'Задачи не выбраны'})
    from django.db.models import Q
    to_delete = TaskNode.objects.filter(id__in=task_ids)
    count = to_delete.count()
    # Родительские задачи удалятся вместе с подзадачами (CASCADE)
    to_delete.delete()
    return JsonResponse({'status': 'ok', 'deleted': count})


@require_POST
def bulk_update_tasks(request):
    task_ids = request.POST.getlist('task_ids')
    if not task_ids:
        return JsonResponse({'status': 'error', 'message': 'Задачи не выбраны'})

    updates = {}
    field_mapping = {
        'project_site': 'project_site_id',
        'building_number': 'building_number_id',
        'status': 'status_id',
        'category': 'category_id',
        'contractor': 'contractor_id',
        'design_chapter': 'design_chapter_id',
        'due_date': 'due_date',
        'price': 'price',
    }

    for field, db_field in field_mapping.items():
        value = request.POST.get(field)
        if value:
            if field in ['status', 'category', 'contractor', 'design_chapter', 'building_number']:
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


@login_required
@require_POST
def save_user_settings(request):
    settings, _ = UserSettings.objects.get_or_create(user=request.user)

    bool_fields = ['inherit_props', 'default_tree_view', 'default_project_site', 'default_building',
                   'default_category', 'default_status', 'default_contractor']
    for field in bool_fields:
        if field in request.POST:
            setattr(settings, field, request.POST.get(field) in ('true', 'True', '1', 'on'))

    if request.POST.get('new_task_position') in ('top', 'bottom'):
        settings.new_task_position = request.POST['new_task_position']

    if 'active_project_id' in request.POST:
        active_id = request.POST.get('active_project_id') or None
        settings.active_project_id = int(active_id) if active_id else None

    if 'column_visibility' in request.POST:
        try:
            settings.column_visibility = json.loads(request.POST['column_visibility'])
        except (TypeError, ValueError):
            pass

    if 'column_widths' in request.POST:
        try:
            settings.column_widths = json.loads(request.POST['column_widths'])
        except (TypeError, ValueError):
            pass

    if 'column_order' in request.POST:
        try:
            order = json.loads(request.POST['column_order'])
            if isinstance(order, list):
                settings.column_order = order
        except (TypeError, ValueError):
            pass

    if 'panel_fields' in request.POST:
        try:
            fields = json.loads(request.POST['panel_fields'])
            if isinstance(fields, dict):
                settings.panel_fields = fields
        except (TypeError, ValueError):
            pass

    if 'page_length' in request.POST:
        try:
            value = int(request.POST['page_length'])
            settings.page_length = value if value > 0 else -1
        except (TypeError, ValueError):
            pass

    settings.save()
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def save_filter_state(request):
    """Сохранение состояния фильтров в БД (по проекту или общее). auto_save=false — забыть состояние."""
    auto_save = request.POST.get('auto_save') == 'true'

    settings, _ = UserSettings.objects.get_or_create(user=request.user)
    settings.auto_save = auto_save
    settings.save()

    params = {field: request.POST.get(field, '') for field in FILTER_FIELDS}
    project_id = params.get('project_site') or None
    if project_id:
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            project_id = None

    if not auto_save:
        TaskFilterState.objects.filter(user=request.user, project_site_id=project_id).delete()
        return JsonResponse({'status': 'ok', 'auto_save': False})

    state, _ = TaskFilterState.objects.get_or_create(user=request.user, project_site_id=project_id)
    state.params = params
    state.save()
    return JsonResponse({'status': 'ok', 'auto_save': True})


def filter_tasks_ajax(request):
    from django.template.loader import render_to_string
    # Всегда дерево: задачи под фильтр + их подзадачи (поддеревья) в порядке MPTT
    filter_dict = create_filter_qs(request, StaticFilterSettings.filtered_value_list, data=request.GET)
    date_filter = data_filter_qs(request, 'due_date', data=request.GET)
    qs = _task_subtree_qs(filter_dict, date_filter)

    table = TaskNodeTable(qs)
    table.view_mode = 'tree'
    RequestConfig(request, paginate=False).configure(table)
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
        # __next__: из POST (save), из GET-параметра, иначе fallback на карточку задачи
        next_url = (
            self.request.POST.get('__next__')
            or self.request.GET.get('next')
            or self.request.META.get('HTTP_REFERER')
            or reverse('task_detail', args=[self.object.pk])
        )
        context['i__next__'] = next_url
        return context

    def get_success_url(self):
        return self.request.POST.get('__next__') or reverse('custom_task_view')


class SubTaskDeleteView(TaskDeleteView):
    template_name = 'ProjectTDL/Delete_Form.html'


@login_required
def task_detail(request, pk):
    """Рабочая карточка задачи: удобнее админки — письма, подзадачи в одном месте."""
    task = get_object_or_404(
        TaskNode.objects.select_related(
            'project_site', 'building_number__name', 'design_chapter',
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
    """Дерево задач: плоская таблица с иерархией (родитель/дети) + фильтры."""
    roots = TaskNode.objects.filter(parent__isnull=True).select_related(
        'project_site', 'building_number__name', 'design_chapter',
        'contractor', 'status', 'category', 'owner', 'parent'
    ).prefetch_related('children')

    project = request.GET.get('project_site')
    if project:
        roots = roots.filter(project_site_id=project)
    building = request.GET.get('building_number')
    if building:
        roots = roots.filter(building_number__name_id=building)
    design = request.GET.get('design_chapter')
    if design:
        roots = roots.filter(design_chapter_id=design)
    status = request.GET.get('status')
    if status:
        roots = roots.filter(status_id=status)
    category = request.GET.get('category')
    if category:
        roots = roots.filter(category_id=category)
    contractor = request.GET.get('contractor')
    if contractor:
        roots = roots.filter(contractor_id=contractor)

    context = {
        'roots': roots,
        'all_project_sites': ProjectSite.objects.all().order_by('name'),
        'all_statuses': Status.objects.all().order_by('name'),
        'all_categories': Category.objects.all().order_by('name'),
        'all_contractors': Contractor.objects.all().order_by('name'),
        'all_building_types': BuildingType.objects.all().order_by('name'),
        'all_design_chapters': DesignChapter.objects.all().order_by('short_name'),
    }
    return render(request, 'ProjectTDL/task_tree.html', context)


@login_required
def generate_custom_report(request):
    """View для генерации HTML отчета по выбранным задачам (как в админке)."""
    task_ids = []
    for value in request.GET.getlist('task_ids'):
        task_ids.extend(value.split(','))
    task_ids = [t for t in task_ids if t]

    if not task_ids:
        return HttpResponse("Не выбраны задачи для отчета")

    tasks = TaskNode.objects.filter(id__in=task_ids).select_related(
        'project_site', 'building_number__name',
        'design_chapter', 'contractor', 'status', 'category', 'contract'
    ).prefetch_related('due_date_history')

    admin_url = None
    if request:
        try:
            admin_url = request.build_absolute_uri(reverse('custom_task_view'))
        except Exception:
            admin_url = None

    html_report = ReportGenerator.generate_html_report(tasks, request=request, admin_url=admin_url)

    response = HttpResponse(html_report, content_type='text/html')
    response['Content-Disposition'] = 'inline; filename="custom_tasks_report.html"'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'

    return response









