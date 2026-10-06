"""Сводка дня (блок 34, фича): непрочитанное, сроки недели, платежи.

Семантика закрытых статусов задач — по имени (Status без флага):
CLOSED_STATUS_NAMES править под справочник владельца.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

#: Имена статусов, считающихся закрытыми (casefold-сравнение).
#: Владелец: дополни под свой справочник StaticData.Status.
CLOSED_STATUS_NAMES = frozenset({
    'закрыто', 'закрыта', 'выполнено', 'готово',
    'closed', 'done',
})

UPCOMING_DAYS = 14


def dashboard_data(today=None):
    """Чистая сборка сводки (без request): для view и тестов."""
    from Emails.models import Email
    from ProjectContract.models import ContractPayments
    from ProjectTDL.models import TaskNode

    today = today or datetime.date.today()
    horizon = today + datetime.timedelta(days=UPCOMING_DAYS)

    inbox_unread = Email.objects.filter(
        folder='inbox', is_read=False).count()
    drafts = Email.objects.filter(folder='drafts').count()

    tasks = TaskNode.objects.filter(node_type='task').select_related(
        'project_site', 'status')
    due_week = list(tasks.filter(
        due_date__gte=today, due_date__lte=horizon,
    ).order_by('due_date')[:20])
    overdue_all = list(tasks.filter(
        due_date__lt=today,
    ).order_by('due_date')[:50])
    overdue = [
        t for t in overdue_all
        if (t.status.name if t.status_id else '').casefold()
        not in CLOSED_STATUS_NAMES
    ]

    payments = list(ContractPayments.objects.filter(
        made_payment=False, due_date__gte=today, due_date__lte=horizon,
    ).select_related('contract').order_by('due_date')[:20])
    payments_total = sum(
        (p.price or Decimal('0') for p in payments), Decimal('0'))

    recent = list(Email.objects.filter(folder='inbox').select_related(
        'project_site', 'contractor').order_by('-email_stamp')[:5])

    return {
        'inbox_unread': inbox_unread,
        'drafts': drafts,
        'due_week': due_week,
        'overdue': overdue,
        'payments': payments,
        'payments_total': payments_total,
        'recent': recent,
    }


@login_required
def dashboard(request):
    """Страница сводки."""
    return render(request, 'dashboard.html', dashboard_data())
