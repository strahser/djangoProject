# -*- coding: utf-8 -*-
"""Карточка договора ProjectContract (HTMX-вкладки, напоминания, файлы).

Дашборд/cashflow → views_cashflow, ДДС → views_dds, платежи → views_payments.
_build_cashflow_chart — намеренный ре-экспорт (тест tests.py:675 тянет из views).
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Contract
from .views_cashflow import _build_cashflow_chart  # noqa: F401 (ре-экспорт для тестов)


CONTRACT_TABS = ('payments', 'tasks', 'stages', 'history', 'docs')




@login_required
def contract_detail(request, pk):
    """Карточка договора с HTMX-вкладками (DMC-4).

    Первая вкладка (Оплаты) рендерится сразу; остальные подгружаются
    по hx-get → contract_tab без full-page reload.
    """
    contract = get_object_or_404(
        Contract.objects.select_related('project_site', 'contractor', 'client'),
        pk=pk)
    from ProjectContract.services import contract_totals
    totals = contract_totals(contract)
    payments = list(contract.contractpayments_set.order_by('due_date'))
    paid_total = sum(p.price or 0 for p in payments if p.made_payment)
    total_price = sum(p.price or 0 for p in payments)
    return render(request, 'ProjectContract/contract_detail.html', {
        'contract': contract,
        'tabs': CONTRACT_TABS,
        'tab': 'payments',
        'payments': payments,
        'paid_total': paid_total,
        'total_price': total_price,
        'totals': totals,
    })




@login_required
def contract_tab(request, pk, tab):
    """Фрагмент вкладки карточки договора для HTMX (DMC-4)."""
    from ProjectTDL.models import TaskNode
    from ProjectContract.models import ContractChangeLog
    contract = get_object_or_404(Contract, pk=pk)
    if tab == 'payments':
        payments = contract.contractpayments_set.order_by('due_date')
        return render(request, 'ProjectContract/_tab_payments.html', {
            'contract': contract,
            'tab': tab,
            'payments': payments,
            'paid_total': sum(p.price or 0 for p in payments if p.made_payment),
            'total_price': sum(p.price or 0 for p in payments),
        })
    if tab == 'tasks':
        tasks = TaskNode.objects.filter(contract=contract).order_by('name')
        linked_total = sum(t.total_paid for t in tasks)
        return render(request, 'ProjectContract/_tab_tasks.html', {
            'contract': contract,
            'tab': tab,
            'tasks': tasks,
            'linked_total': linked_total,
        })
    if tab == 'stages':
        steps = contract.stage_logs.select_related('user').order_by('-date', '-id')
        reminders = contract.reminders.filter(
            task__isnull=True, is_done=False).select_related(
            'recipient').order_by('due_date', 'id')
        from django.contrib.auth.models import User
        return render(request, 'ProjectContract/_tab_stages.html', {
            'contract': contract,
            'tab': tab,
            'steps': steps,
            'reminders': reminders,
            'reminder_users': User.objects.filter(
                is_active=True).order_by('username'),
        })
    if tab == 'history':
        history = (ContractChangeLog.objects.filter(contract=contract)
                   .select_related('user').order_by('-creation_stamp')[:100])
        return render(request, 'ProjectContract/_tab_history.html', {
            'contract': contract,
            'tab': tab,
            'history': history,
        })
    if tab == 'docs':
        attachments = contract.attachments.select_related('uploaded_by')[:20]
        return render(request, 'ProjectContract/_tab_docs.html', {
            'contract': contract,
            'tab': tab,
            'attachments': attachments,
        })
    return HttpResponse('Неизвестная вкладка', status=404)




def _parse_reminder_form(request):
    """due_date/message/recipient из POST; (due_date, message, recipient)."""
    from django.contrib.auth.models import User
    from django.utils.dateparse import parse_date
    due = parse_date(request.POST.get('due_date') or '')
    if due is None:
        return None, None, None
    message = (request.POST.get('message') or '').strip()[:255]
    recipient = None
    rid = request.POST.get('recipient') or ''
    if rid:
        recipient = User.objects.filter(pk=rid, is_active=True).first()
    return due, message, recipient




@login_required
@require_POST
def contract_reminder_add(request, pk):
    """Кнопка «Напомнить» в карточке договора (DMX-2)."""
    from .models import ContractReminder
    from .services import log_change
    contract = get_object_or_404(Contract, pk=pk)
    due, message, recipient = _parse_reminder_form(request)
    if due is None:
        messages.error(request, 'Укажите дату напоминания')
        return redirect('contract_detail', pk=pk)
    reminder = ContractReminder.objects.create(
        contract=contract, due_date=due, message=message,
        recipient=recipient, created_by=request.user)
    log_change(contract=contract, action='reminder:create',
               details=f'напомнить до {due:%d.%m.%Y}'
                       + (f': {message}' if message else ''),
               user=request.user)
    messages.success(request, f'Напоминание на {due:%d.%m.%Y} создано')
    return redirect('contract_detail', pk=pk)




@login_required
@require_POST
def contract_attachment_add(request, pk):
    """Загрузить файл к договору (DMX-4, C11)."""
    from .models import Attachment
    from .services import log_change
    contract = get_object_or_404(Contract, pk=pk)
    f = request.FILES.get('file')
    if not f:
        messages.error(request, 'Выберите файл')
        return redirect('contract_detail', pk=pk)
    Attachment.objects.create(file=f, contract=contract,
                              uploaded_by=request.user,
                              description=(request.POST.get('description') or '')[:255])
    log_change(contract=contract, action='contract:attach',
               details=f.name, user=request.user)
    messages.success(request, f'Файл «{f.name}» загружен')
    return redirect('contract_detail', pk=pk)




@login_required
@require_POST
def reminder_toggle(request, pk):
    """Закрыть/переоткрыть напоминание (DMX-2)."""
    from .models import ContractReminder
    from .services import log_change
    reminder = get_object_or_404(ContractReminder, pk=pk)
    reminder.is_done = not reminder.is_done
    reminder.save(update_fields=['is_done'])
    log_change(contract=reminder.contract, action='reminder:done'
               if reminder.is_done else 'reminder:reopen',
               details=str(reminder), user=request.user)
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if next_url:
        return redirect(next_url)
    if reminder.contract_id:
        return redirect('contract_detail', pk=reminder.contract_id)
    return redirect('contract_dashboard')
