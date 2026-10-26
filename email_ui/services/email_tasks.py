# -*- coding: utf-8 -*-
"""Письмо → задача: общая логика кнопки «Создать задачу» и действия правил.

Связей две, и они живут раздельно:

* ``Email.tasks`` (M2M) — его читает блок «Задачи письма» на странице письма;
* ``EmailTaskLink`` — тип связи, автор и админский inline.

Создаём обе, иначе задача «теряется» в одном из интерфейсов.
"""
from typing import Optional, Tuple

from loguru import logger

from email_ui.models import EmailTaskLink


def task_name_from_email(email) -> str:
    """Название задачи из письма: тема (TaskNode.name — max 150 символов)."""
    subject = ' '.join((email.subject or '').split())
    if not subject:
        stamp = email.email_stamp or email.creation_stamp
        subject = f'Письмо от {stamp:%d.%m.%Y}' if stamp else 'Письмо без темы'
    return subject[:150]


def resolve_project_id(email, user) -> Optional[int]:
    """Проект для задачи: из письма, иначе активный проект пользователя.

    ``TaskNode.project_site`` обязателен, а у большинства писем проект не
    заполнен — без этого фолбэка создание задачи из письма падало бы.
    """
    if email.project_site_id:
        return email.project_site_id
    from ProjectTDL.models import UserSettings
    settings = UserSettings.objects.filter(user=user).first()
    return settings.active_project_id if settings else None


def create_task_from_email(
    email,
    user,
    *,
    name: Optional[str] = None,
    project_site_id: Optional[int] = None,
) -> Tuple[object, bool]:
    """Создать задачу из письма и прикрепить письмо.

    Возвращает ``(task, created)``. Повторный вызов с тем же названием не
    плодит дубли: возвращает уже созданную из этого письма задачу.
    Бросает ``ValueError``, если проект определить нельзя.
    """
    from ProjectTDL.services.task_mutations import create_task_with_defaults

    name = ' '.join((name or task_name_from_email(email)).split())[:150]

    # Защита от двойного клика/повторного прогона правила.
    existing = (email.task_links
                .filter(link_type='created_from', task_node__name=name)
                .select_related('task_node')
                .first())
    if existing:
        return existing.task_node, False

    project_site_id = project_site_id or resolve_project_id(email, user)
    if not project_site_id:
        raise ValueError(
            'у письма не указан проект, а активный проект не выбран')

    task = create_task_with_defaults(
        owner=user,
        name=name,
        project_site_id=project_site_id,
        contractor_id=email.contractor_id,
    )
    email.tasks.add(task)
    EmailTaskLink.objects.create(
        email=email,
        task_node=task,
        link_type='created_from',
        created_by=user,
    )
    logger.info(
        f'Письмо id={email.pk} превращено в задачу id={task.pk} '
        f'({user.username})'
    )
    return task, True
