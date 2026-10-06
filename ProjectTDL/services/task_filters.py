# -*- coding: utf-8 -*-
"""Фильтры и поддеревья задач (блок 4; переезд из views без смены поведения).

Правила наследования (_inherit_filter_q -> inherit_filter_q): пустое поле
подзадачи = «как у родителя» (строка остаётся), явно чужое значение
(напр. «Закрыто» при фильтре «Открыто») = строка скрывается.
"""
from django.db.models import Q

from ProjectTDL.models import TaskNode, TaskFilterState, UserSettings
from ProjectTDL.Tables import StaticFilterSettings, annotate_has_children


def inherit_filter_q(filter_dict, date_filter):
    """Q для строк поддерева: совпадение с фильтром ИЛИ пустое поле."""
    result = Q()
    for key, values in (filter_dict or {}).items():
        base = key.split('__')[0]
        result &= Q(**{key: values}) | Q(**{f'{base}__isnull': True})
    for key, value in (date_filter or {}).items():
        base = key.split('__')[0]
        result &= Q(**{key: value}) | Q(**{f'{base}__isnull': True})
    return result


def task_subtree_qs(filter_dict, date_filter):
    """Задачи под фильтром + их поддеревья (MPTT), с has_children-аннотацией."""
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
    qs = TaskNode.objects.filter(bounds)
    if filter_dict or date_filter:
        qs = qs.filter(inherit_filter_q(filter_dict, date_filter))
    return annotate_has_children(qs.select_related(
        *StaticFilterSettings.filtered_value_list
    ).order_by('tree_id', 'lft'))


def get_filter_state(user):
    """Сохранённое состояние фильтров: по активному проекту, иначе общее."""
    if not getattr(user, 'is_authenticated', False):
        return None
    settings = UserSettings.objects.filter(user=user).first()
    active_project_id = settings.active_project_id if settings else None
    if active_project_id:
        state = TaskFilterState.objects.filter(
            user=user, project_site_id=active_project_id).first()
        if state:
            return state
    return TaskFilterState.objects.filter(
        user=user, project_site__isnull=True).first()


def cascade_options(project_site_id=None, building_type_id=None):
    """Опции каскадных фильтров (бывший cascade_filter_options).

    Возвращает dict statuses/categories/contractors/buildings.
    Правило «пусто → все» сохранено 1:1.
    """
    from ProjectContract.models import Contractor
    from StaticData.models import Category, Status
    from StaticData.models import BuildingType

    def _all_entries():
        return {
            'statuses': [{'pk': s.pk, 'name': s.name}
                         for s in Status.objects.all().order_by('name')],
            'categories': [{'pk': c.pk, 'name': c.name}
                           for c in Category.objects.all().order_by('name')],
            'contractors': [{'pk': c.pk, 'name': c.name}
                            for c in Contractor.objects.all().order_by('name')],
            'buildings': [{'pk': b.pk, 'name': b.name}
                          for b in BuildingType.objects.all().order_by('name')],
        }

    if not project_site_id and not building_type_id:
        return _all_entries()

    qs = TaskNode.objects.filter(node_type='task')
    if project_site_id:
        qs = qs.filter(project_site_id=project_site_id)
    if building_type_id:
        qs = qs.filter(building_number__name_id=building_type_id)

    def _field_items(field_name, related_name, model_class):
        vals = list(qs.filter(**{field_name + '__isnull': False})
                    .order_by(related_name + '__name')
                    .values_list(field_name + '_id', flat=True).distinct())
        if vals:
            return [{'pk': obj.pk, 'name': obj.name}
                    for obj in model_class.objects.filter(pk__in=vals).order_by('name')]
        return [{'pk': obj.pk, 'name': obj.name}
                for obj in model_class.objects.all().order_by('name')]

    def _building_items():
        # Типы зданий каскадируются от ПРОЕКТА (не от выбранного типа).
        bqs = TaskNode.objects.filter(node_type='task')
        if project_site_id:
            bqs = bqs.filter(project_site_id=project_site_id)
        vals = list(bqs.filter(building_number__isnull=False,
                               building_number__name__isnull=False)
                    .values_list('building_number__name_id', flat=True).distinct())
        if vals:
            return [{'pk': obj.pk, 'name': obj.name}
                    for obj in BuildingType.objects.filter(pk__in=vals).order_by('name')]
        return [{'pk': obj.pk, 'name': obj.name}
                for obj in BuildingType.objects.all().order_by('name')]

    return {
        'statuses': _field_items('status', 'status', Status),
        'categories': _field_items('category', 'category', Category),
        'contractors': _field_items('contractor', 'contractor', Contractor),
        'buildings': _building_items(),
    }
