"""DMX-1: аудит TaskNode в общий журнал ContractChangeLog (C4).

create/update/delete каждой задачи журналируются с user (текущий
пользователь запроса через CurrentUserMiddleware; None = система/скрипт).
Обновления без изменения отслеживаемых полей (MPTT-перестроения,
update_stamp) в журнал не попадают.
"""
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from ProjectContract.services import (
    TASK_TRACKED_FIELDS,
    log_task_change,
    task_diff,
)

from .models import TaskNode

# Снимки до сохранения: pre_save кладёт, post_save забирает и удаляет.
_OLD_INSTANCES = {}


@receiver(pre_save, sender=TaskNode)
def _snapshot_task(sender, instance, **kwargs):
    if kwargs.get('raw') or instance.pk is None:
        return
    try:
        _OLD_INSTANCES[instance.pk] = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:  # pragma: no cover — гонка pre/post
        pass


@receiver(post_save, sender=TaskNode)
def _log_task_save(sender, instance, created, update_fields=None, **kwargs):
    if kwargs.get('raw'):
        _OLD_INSTANCES.pop(instance.pk, None)
        return
    if created:
        log_task_change(instance, 'task:create', f'«{instance.name}»')
        return
    if update_fields is not None and not (
            set(update_fields) & set(TASK_TRACKED_FIELDS)):
        _OLD_INSTANCES.pop(instance.pk, None)
        return
    old = _OLD_INSTANCES.pop(instance.pk, None)
    if old is None:  # pragma: no cover — не должно случаться
        log_task_change(instance, 'task:update', 'изменена')
        return
    changes = task_diff(old, instance)
    if changes:
        log_task_change(instance, 'task:update', '; '.join(changes))


@receiver(post_delete, sender=TaskNode)
def _log_task_delete(sender, instance, **kwargs):
    if kwargs.get('raw'):
        return
    # queryset.delete() тоже шлёт post_delete на каждый объект —
    # bulk_delete_tasks покрывается автоматически (C4).
    # Запись создаётся ПОСЛЕ удаления строки задачи, поэтому FK task
    # не ставим (иначе висячая ссылка): имя/id — в details.
    from django.core.exceptions import ObjectDoesNotExist

    from ProjectContract.services import log_change
    try:
        contract = instance.contract
    except ObjectDoesNotExist:
        contract = None
    log_change(contract=contract, action='task:delete',
               details=f'«{instance.name}» (id={instance.pk})')
