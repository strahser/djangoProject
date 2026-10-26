# -*- coding: utf-8 -*-
"""P2: вьюхи правил автоматизации email_ui (вынесено из views.py 1:1).

rule_run_now прогоняет правила в daemon-потоке (services/rule_runner):
синхронный обход всей базы вешал запрос на минуты.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .forms import EmailRuleForm
from .models import EmailRule
from .services.modal_forms import save_modal_form


@login_required
def rules_list(request):
    """Список правил автоматизации."""
    rules = EmailRule.objects.all().order_by('-priority')
    return render(request, 'email_ui/partials/rules_list.html', {'rules': rules})


@login_required
def rule_create_modal(request):
    """Модальное окно создания правила."""
    form = EmailRuleForm()
    return render(request, 'email_ui/partials/rule_modal.html', {
        'form': form, 'mode': 'create',
    })


@login_required
@require_http_methods(['POST'])
def rule_create(request):
    """Создание правила (AJAX)."""
    form = EmailRuleForm(request.POST)

    def _save_rule():
        rule = form.save(commit=False)
        rule.created_by = request.user
        rule.save()
        return rule

    return save_modal_form(
        request, form, template='email_ui/partials/rule_modal.html',
        mode='create',
        message=lambda rule: f'Правило "{rule.name}" создано',
        save=_save_rule)


@login_required
def rule_edit_modal(request, pk):
    """Модальное окно редактирования правила."""
    rule = get_object_or_404(EmailRule, pk=pk)
    form = EmailRuleForm(instance=rule)
    return render(request, 'email_ui/partials/rule_modal.html', {
        'form': form, 'rule': rule, 'mode': 'edit',
    })


@login_required
@require_http_methods(['POST'])
def rule_edit(request, pk):
    """Редактирование правила (AJAX)."""
    rule = get_object_or_404(EmailRule, pk=pk)
    form = EmailRuleForm(request.POST, instance=rule)
    return save_modal_form(
        request, form, template='email_ui/partials/rule_modal.html',
        mode='edit', message='Правило обновлено',
        extra={'rule': rule})


@login_required
@require_http_methods(['POST'])
def rule_toggle(request, pk):
    """Включить/выключить правило."""
    rule = get_object_or_404(EmailRule, pk=pk)
    rule.is_active = not rule.is_active
    rule.save(update_fields=['is_active'])
    return JsonResponse({'is_active': rule.is_active})


@login_required
@require_http_methods(['POST'])
def rule_run_now(request, pk):
    """Запустить правило для всех писем (в фоне — блок P2).

    Прогон по всей базе синхронно вешал запрос на минуты; теперь движок
    работает в daemon-потоке, итог — в EmailAutomationLog и logs/email_ui.log.
    """
    rule = get_object_or_404(EmailRule, pk=pk)
    from .services.rule_runner import run_rule_async
    run_rule_async(rule)
    messages.info(
        request,
        f'Правило "{rule.name}" запущено в фоне — результат в журнале '
        f'автоматизации')
    return HttpResponse(status=204)
