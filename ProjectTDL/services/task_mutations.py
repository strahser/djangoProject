# -*- coding: utf-8 -*-
"""Мутации задач (блок 4): bulk-обновления и быстрое создание.

Правила валидации сохранены 1:1 из views (включая молчаливое пропускание
невалидных int и запятую в цене bulk). queryset.update() не шлёт сигналов —
вместо построчного аудита пишется суммарный task:bulk_update (как раньше).
"""
from django.db import transaction

from ProjectContract.services import log_change
from ProjectTDL.models import TaskNode, UserSettings

#: POST-поле -> поле модели (бывший field_mapping bulk_update_tasks).
BULK_FIELD_MAP = {
    'project_site': 'project_site_id',
    'building_number': 'building_number_id',
    'status': 'status_id',
    'category': 'category_id',
    'contractor': 'contractor_id',
    'design_chapter': 'design_chapter_id',
    'due_date': 'due_date',
    'price': 'price',
}

_INT_FIELDS = frozenset(
    {'status', 'category', 'contractor', 'design_chapter', 'building_number'})


def parse_bulk_updates(raw):
    """Сырые POST-данные -> dict полей модели (невалидное молча пропускается)."""
    updates = {}
    get = raw.get if hasattr(raw, 'get') else (lambda k, d=None: raw.get(k, d))
    for field, db_field in BULK_FIELD_MAP.items():
        value = get(field)
        if not value:
            continue
        if field in _INT_FIELDS:
            try:
                updates[db_field] = int(value)
            except (ValueError, TypeError):
                continue
        elif field == 'price':
            try:
                updates[db_field] = float(str(value).replace(',', '.'))
            except (ValueError, TypeError):
                continue
        else:
            updates[db_field] = value
    return updates


def apply_bulk_update(task_ids, updates, user):
    """Массовое обновление + суммарная запись аудита, в одной транзакции.

    Возвращает dict(updated_count, ids, updated_fields).
    """
    qs = TaskNode.objects.filter(id__in=task_ids)
    ids = list(qs.values_list('pk', flat=True))
    with transaction.atomic():
        updated_count = qs.update(**updates)
        # queryset.update() не шлёт сигналов — суммарная запись (DMX-1)
        log_change(action='task:bulk_update',
                   details=f'Массовое обновление {updated_count} задач '
                           f'(ids {ids[:20]}): {sorted(updates)}',
                   user=user)
    return {'updated_count': updated_count, 'ids': ids,
            'updated_fields': list(updates.keys())}


#: Справочник -> (модель, поле) связей для проверки перед удалением (блок 15).
#: Удаление подрядчика/проекта каскадно сносит задачи и договоры, удаление
#: статуса роняет БД (DO_NOTHING), категории — молча отвязывает задачи.
_REFERENCE_USAGE = {
    'project_site': [('ProjectTDL.TaskNode', 'project_site'),
                     ('ProjectContract.Contract', 'project_site')],
    'building_number': [('ProjectTDL.TaskNode', 'building_number')],
    'design_chapter': [('ProjectTDL.TaskNode', 'design_chapter')],
    'contractor': [('ProjectTDL.TaskNode', 'contractor'),
                   ('ProjectContract.Contract', 'contractor'),
                   ('ProjectContract.Contract', 'client')],
    'status': [('ProjectTDL.TaskNode', 'status')],
    'category': [('ProjectTDL.TaskNode', 'category')],
}


def _resolve_model(dotted):
    from django.apps import apps
    return apps.get_model(dotted)


def reference_usage(model_key, obj_id):
    """Использование справочника: [(модель, поле, count)] с count > 0."""
    used = []
    for dotted, field in _REFERENCE_USAGE.get(model_key, ()):
        model = _resolve_model(dotted)
        n = model.objects.filter(**{field + '_id': obj_id}).count()
        if n:
            used.append((dotted, field, n))
    return used


def delete_reference(model, model_key, obj_id):
    """Удаление записи справочника с защитой от каскадных потерь.

    Возвращает dict(ok, message). Занятая запись не удаляется.
    Несуществующий id — ok (как раньше: filter().delete() молча пуст).
    """
    used = reference_usage(model_key, obj_id)
    if used:
        details = ', '.join(f'{m}.{f}: {n}' for m, f, n in used)
        return {'ok': False,
                'message': f'Запись используется ({details}) — удаление заблокировано'}
    model.objects.filter(pk=obj_id).delete()
    return {'ok': True, 'message': ''}


def _inherit_enabled(user_settings):
    return bool(user_settings and (
        user_settings.inherit_props
        or user_settings.default_project_site
        or user_settings.default_building
        or user_settings.default_category
        or user_settings.default_status
        or user_settings.default_contractor
    ))


def create_task_with_defaults(*, owner, name, project_site_id=None,
                              status_id=None, category_id=None,
                              contractor_id=None, building_number_id=None):
    """Быстрое создание задачи + наследование от последней задачи проекта.

    Правило (бывший quick_create_task): при включённом inherit_props/любом
    default_* незаполненные поля берутся из последней задачи проекта
    (order_by -pk). Гонка двух созданий сохраняется как есть (см. гарды).
    """
    user_settings = UserSettings.objects.filter(user=owner).first()
    if _inherit_enabled(user_settings) and project_site_id:
        last_task = TaskNode.objects.filter(
            node_type='task', project_site_id=project_site_id
        ).order_by('-pk').first()
        if last_task:
            status_id = status_id or last_task.status_id or None
            category_id = category_id or last_task.category_id or None
            contractor_id = contractor_id or last_task.contractor_id or None
            building_number_id = (building_number_id
                                  or last_task.building_number_id or None)
    return TaskNode.objects.create(
        name=name,
        node_type='task',
        owner=owner,
        project_site_id=project_site_id,
        status_id=status_id,
        category_id=category_id,
        contractor_id=contractor_id,
        building_number_id=building_number_id,
    )
