"""Сервисный слой расчёта платежей (Ф0 рефакторинга).

Заменяет магию в ``ContractPayments.save()`` и ``eval()`` в admin:
чистые функции без побочных эффектов + одна точка пересчёта цепочки дат
через ``bulk_update`` (без рекурсивных save).
"""
import re
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

_SIMPLE_FORMULA = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*\*\s*(\d+(?:\.\d+)?)\s*$')


def parse_simple_formula(text):
    """Разобрать старую custom_formula вида 'BASE*FACTOR'.

    Возвращает (base_amount, factor) как Decimal или None, если строка
    не соответствует безопасной грамматике. Никакого eval.
    """
    m = _SIMPLE_FORMULA.match(text or '')
    if not m:
        return None
    return Decimal(m.group(1)), Decimal(m.group(2))


def compute_price(payment):
    """Посчитать цену платежа по его типу расчёта.

    Возвращает Decimal или None (None = оставить введённую вручную цену).
    Не ходит в БД лишний раз: использует payment.contract, если он уже
    подгружен, иначе — один точечный запрос цены договора.
    """
    calc = getattr(payment, 'calc_type', None) or 'manual'
    pct = getattr(payment, 'percent', None)
    if calc not in ('percent_of_contract', 'percent_of_base', 'percent_of_parent') \
            or not pct:
        return None
    if calc == 'percent_of_contract':
        contract = getattr(payment, 'contract', None)
        base = getattr(contract, 'price', None) if contract is not None else None
        if base is None and getattr(payment, 'contract_id', None):
            from .models import Contract
            base = Contract.objects.filter(pk=payment.contract_id)\
                .values_list('price', flat=True).first()
        if base is None:
            return None
    elif calc == 'percent_of_parent':
        parent = payment.parent if getattr(payment, 'parent_id', None) else None
        if parent is None or parent.price is None:
            return None
        base = parent.price
    else:
        base = getattr(payment, 'base_amount', None)
        if base is None:
            return None
    return (Decimal(str(pct)) * Decimal(base))\
        .quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def compute_own_dates(payment):
    """Пересчитать собственные даты платежа in-memory (без сохранения).

    Дисциплина цепочки (была размазана по save/update_*):
    - есть родитель → start_date подтягивается к due_date родителя;
    - due_date выводится из start+duration, только если due пуст или
      старт/длит изменились, а due правили не вручную;
    - явно заданный due_date вручную — священен (переключение статуса
      оплаты и прочие save его не затирают).
    """
    from .models import ContractPayments
    old = None
    if payment.pk:
        old = ContractPayments.objects.filter(pk=payment.pk).values(
            'start_date', 'duration', 'due_date').first()
    snapped = False
    if getattr(payment, 'parent_id', None):
        parent = payment.parent  # из кэша или один точечный запрос
        if parent is not None and parent.due_date \
                and payment.start_date != parent.due_date:
            payment.start_date = parent.due_date
            snapped = True
    if payment.start_date and payment.duration:
        derived = payment.start_date + timedelta(days=payment.duration)
        if payment.due_date is None:
            payment.due_date = derived
        elif old is not None and payment.due_date == old['due_date'] \
                and (snapped or (payment.start_date, payment.duration)
                     != (old['start_date'], old['duration'])):
            payment.due_date = derived
        # иначе: create с явным due или ручная правка due — не трогаем


def propagate_dates(payment):
    """Пересчитать даты всей цепочки потомков (BFS, один bulk_update).

    Возвращает число обновлённых платежей. Защита от циклов через visited.
    Цены потомков НЕ трогает: они пересчитываются только при собственном
    сохранении (раньше рекурсивный save делал это incidental — убрано).
    """
    from .models import ContractPayments
    updated = []
    seen = {payment.pk}
    frontier = [(payment.pk, payment.due_date)]
    while frontier:
        parent_id, parent_due = frontier.pop()
        for child in ContractPayments.objects.filter(parent_id=parent_id):
            if child.pk in seen:
                continue
            seen.add(child.pk)
            if parent_due:
                child.start_date = parent_due
            if child.start_date and child.duration:
                child.due_date = child.start_date + timedelta(days=child.duration)
            updated.append(child)
            frontier.append((child.pk, child.due_date))
    if updated:
        ContractPayments.objects.bulk_update(updated, ['start_date', 'due_date'])
    return len(updated)


def log_change(contract=None, payment=None, task=None, action='', details='', user=None):
    """Записать событие в журнал изменений (C4).

    user=None или аноним — пишется как системное (агент/скрипт).
    Если user не передан явно — берётся текущий пользователь запроса
    (CurrentUserMiddleware, DMX-1).
    """
    from .models import ContractChangeLog
    if contract is None and payment is not None:
        contract = payment.contract
    if contract is None and task is not None:
        contract = getattr(task, 'contract', None)
    if user is None:
        user = get_current_user()
    if user is not None and not getattr(user, 'is_authenticated', False):
        user = None
    return ContractChangeLog.objects.create(
        contract=contract, payment=payment, task=task,
        action=action, details=details or '', user=user)


# DMX-1: текущий пользователь запроса для сигналов TaskNode.
# Middleware кладёт request.user в thread-local; сигналы забирают его,
# чтобы каждое изменение задачи попадало в журнал «с user».
import threading as _threading

_current_request_user = _threading.local()


def set_current_user(user):
    _current_request_user.user = user


def get_current_user():
    return getattr(_current_request_user, 'user', None)


# Поля TaskNode, изменения которых журналируются (DMX-1).
# MPTT-служебные (lft/rght/tree_id/level) и штампы — вне журнала.
TASK_TRACKED_FIELDS = (
    'name', 'node_type', 'project_site', 'building_number', 'design_chapter',
    'contractor', 'status', 'category', 'contract', 'parent',
    'price', 'due_date', 'description',
)


def _task_field_display(obj, field):
    """Человекочитаемое значение поля задачи (для FK — имя объекта)."""
    if field in ('price', 'due_date'):
        return str(getattr(obj, field))
    if field == 'description':
        text = (getattr(obj, field) or '').strip()
        return (text[:80] + '…') if len(text) > 80 else (text or '—')
    if field == 'parent':
        parent = getattr(obj, 'parent', None)
        return f'«{parent.name}»' if parent else '—'
    related = getattr(obj, field, None)
    return str(related) if related is not None else '—'


_TASK_SCALAR_FIELDS = frozenset(
    {'name', 'node_type', 'price', 'due_date', 'description'})


def task_diff(old, new):
    """Разница отслеживаемых полей задачи: ['поле: было → стало', ...]."""
    changes = []
    for field in TASK_TRACKED_FIELDS:
        if field in _TASK_SCALAR_FIELDS:
            changed = getattr(old, field) != getattr(new, field)
        else:
            changed = getattr(old, field + '_id') != getattr(new, field + '_id')
        if changed:
            changes.append(
                f'{field}: {_task_field_display(old, field)} → '
                f'{_task_field_display(new, field)}')
    return changes


def log_task_change(task, action, details='', user=None):
    """Записать событие по задаче в общий журнал (DMX-1, C4)."""
    return log_change(task=task, action=action, details=details, user=user)


CONTRACT_TRANSITIONS = {
    'draft': {'active', 'canceled'},
    'active': {'suspended', 'closed', 'canceled'},
    'suspended': {'active', 'closed', 'canceled'},
    'closed': set(),
    'canceled': set(),
}


# DMC-5: последовательность этапов (массив) + разрешённые переходы.
CONTRACT_STAGE_ORDER = (
    'negotiation', 'signing', 'advance', 'execution',
    'acceptance', 'final_payment', 'warranty', 'closed',
)

# Разрешённые переходы из состояния «статус договора».
STAGE_STATUS_RESTRICTIONS = {
    'draft': ('negotiation', 'signing'),
    'suspended': ('negotiation',),
    'closed': tuple(),
    'canceled': tuple(),
}


def get_stage_index(stage):
    from .models import CONTRACT_STAGES
    for i, (code, _name) in enumerate(CONTRACT_STAGES):
        if code == stage:
            return i
    raise ValueError(f'Неизвестный этап: {stage}')


def schedule_contract_stage(contract, stage, date, notes='', user=None):
    """Запланировать следующий шаг договора (напоминание, C3/D9).

    Пишет ContractStageLog (is_next_step=True) и дублирует в поля
    Contract.next_step/next_step_date для ad-hoc напоминаний.
    """
    return _record_stage(contract, stage, date, notes, user, is_next_step=True)


def transition_contract_stage(contract, new_stage, notes='', user=None):
    """Перевести договор на новый этап с валидацией последовательности.

    Разрешено: переход вперёд (по CONTRACT_STAGE_ORDER, допускается шаг на
    несколько стадий сразу — записывается только финальный этап), откат назад
    только со стадий приёмки/окончательного расчёта, повторное фиксирование
    текущей стадии. Запрещено: closed/canceled (задаются через
    transition_contract() / Contract.status) и откат из deep-execution стадий.
    Ограничения статуса — STAGE_STATUS_RESTRICTIONS по Contract.status.
    """
    from datetime import date as _today
    from .models import CONTRACT_STAGES
    if new_stage not in dict(CONTRACT_STAGES):
        raise ValueError(f'Неизвестный этап: {new_stage}')
    if new_stage in ('closed', 'canceled'):
        raise ValueError(
            'Этап «Закрыт/Расторгнут» задаётся через смену статуса '
            'договора (transition_contract), не через переход этапа')
    allowed = STAGE_STATUS_RESTRICTIONS.get(contract.status)
    if allowed is not None and new_stage not in allowed:
        raise ValueError(
            f'Этап {new_stage} недопустим для статуса договора {contract.status}')
    old_stage = contract.stage or 'negotiation'
    old_idx, new_idx = get_stage_index(old_stage), get_stage_index(new_stage)
    if old_idx > new_idx and old_stage not in ('acceptance', 'final_payment'):
        raise ValueError(
            f'Недопустимый переход этапа {old_stage} → {new_stage} (откат '
            f'возможен только со стадий приёмки/окончательного расчёта)')
    return _record_stage(contract, new_stage, date=_today.today(),
                         notes=notes or '', user=user, is_next_step=False)


def _record_stage(contract, stage, date=None, notes='', user=None, is_next_step=False):
    """Общая запись журнала этапа + синхронизация полей Contract.

    is_next_step=False — фактический этап: Contract.stage/next_step* сбрасываются.
    is_next_step=True  — запланированный шаг: Contract.next_step/next_step_date.
    """
    import datetime as _dt
    from .models import ContractStageLog
    date = date or _dt.date.today()
    entry = ContractStageLog.objects.create(
        contract=contract, stage=stage, date=date,
        notes=notes or '', user=user, is_next_step=is_next_step)
    from .models import CONTRACT_STAGES
    label = dict(CONTRACT_STAGES).get(stage, stage)
    if is_next_step:
        contract.next_step = label
        contract.next_step_date = date
        contract.save(update_fields=['next_step', 'next_step_date'])
    else:
        contract.stage = stage
        contract.next_step = ''
        contract.next_step_date = None
        contract.save(update_fields=['stage', 'next_step', 'next_step_date'])
    log_change(contract=contract, action=f'stage:{stage}',
               details=f'{notes or label} ({label})', user=user)
    return entry


def transition_contract(contract, new_status, user=None):
    """Перевести договор в новый статус с проверкой допустимости и журналом."""
    allowed = CONTRACT_TRANSITIONS.get(contract.status, set())
    if new_status not in allowed:
        raise ValueError(
            f'Недопустимый переход статуса договора {contract.status} → {new_status}')
    old = contract.status
    contract.status = new_status
    contract.save(update_fields=['status'])
    log_change(contract=contract, action='status',
               details=f'{old} → {new_status}', user=user)
    return contract


def contract_totals(contract):
    """Свод по платежам договора: цена, факт, прогноз + привязки к задачам (DMC-2)."""
    pays = list(contract.contractpayments_set.all())
    total = lambda pred: sum((p.price or 0) for p in pays if pred(p))
    from ProjectContract.models import PaymentTaskLink
    from ProjectContract.models import ContractEstimate, EstimateConcept
    from ProjectTDL.models import TaskNode
    from django.db.models import Sum
    from datetime import date as _today
    links = PaymentTaskLink.objects.filter(payment__contract=contract)
    linked_total = links.aggregate(total=Sum('amount_applied'))['total'] or 0
    overpaid = 0
    for tn in TaskNode.objects.filter(payment_links__payment__contract=contract).distinct():
        if tn.is_overpaid:
            overpaid += 1
    estimates = list(contract.estimates.all())
    est_total = EstimateConcept.objects.filter(
        estimate__contract=contract).aggregate(total=Sum('amount'))['total'] or 0
    est_overrun = sum(1 for e in estimates if e.is_overrun)
    overdue_steps = (
        contract.stage_logs.filter(is_next_step=True, date__lte=_today.today())
        .count())
    return {
        'price': contract.price or 0,
        'paid': total(lambda p: p.status == 'paid'),
        'guaranteed': total(lambda p: p.status in ('guaranteed', 'approved', 'invoiced')),
        'likely': total(lambda p: p.status in ('high_prob', 'low_prob')),
        'planned': total(lambda p: p.status == 'planned'),
        'count': len(pays),
        'linked_total': linked_total,
        'task_links_count': links.count(),
        'overpaid_tasks': overpaid,
        'estimate_total': est_total,
        'estimate_overrun': est_overrun,
        'stage': contract.stage or 'negotiation',
        'next_step': contract.next_step,
        'next_step_date': contract.next_step_date,
        'overdue_steps': overdue_steps,
    }

def contract_rollup(contract, _seen=None):
    """Свод договора + все субподряды (DMC-2: включает привязки к задачам)."""
    _seen = _seen or set()
    if contract.pk in _seen:
        return None
    _seen.add(contract.pk)
    acc = contract_totals(contract)
    acc['contracts'] = 1
    for child in contract.children.all():
        sub = contract_rollup(child, _seen)
        if sub is None:
            continue
        for key in ('price', 'paid', 'guaranteed', 'likely', 'planned', 'count',
                   'linked_total', 'task_links_count', 'overpaid_tasks',
                   'estimate_total', 'estimate_overrun', 'overdue_steps'):
            acc[key] += sub[key]
        acc['contracts'] += sub['contracts']
    return acc

STATUS_BUCKET = {
    'paid': 'fact',
    'guaranteed': 'guaranteed',
    'approved': 'guaranteed',
    'invoiced': 'guaranteed',
    'high_prob': 'likely',
    'low_prob': 'likely',
    'planned': 'planned',
    'partially_paid': 'guaranteed',  # остаток; факт — отдельной строкой
}


def rebuild_cashflow(contract):
    """Перестроить материализованные строки ДДС договора (Ф2).

    Вызывается сигналом при save/delete платежа. Возвращает число строк.
    Платежи без даты пропускаются (считаются в status_check договора).
    """
    from .models import CashflowEntry
    rows = []
    for p in contract.contractpayments_set.all():
        if p.status == 'paid':
            if (p.paid_date or p.due_date) and (p.paid_amount or p.price):
                rows.append(CashflowEntry(
                    contract=contract, payment=p,
                    date=p.paid_date or p.due_date,
                    amount=p.paid_amount if p.paid_amount is not None else p.price,
                    bucket='fact'))
        elif p.status == 'partially_paid':
            if (p.paid_date or p.due_date) and p.paid_amount:
                rows.append(CashflowEntry(
                    contract=contract, payment=p,
                    date=p.paid_date or p.due_date,
                    amount=p.paid_amount, bucket='fact'))
            rest = (p.price or 0) - (p.paid_amount or 0)
            if p.due_date and rest > 0:
                rows.append(CashflowEntry(
                    contract=contract, payment=p,
                    date=p.due_date, amount=rest, bucket='guaranteed'))
        else:
            if p.due_date and p.price:
                rows.append(CashflowEntry(
                    contract=contract, payment=p,
                    date=p.due_date, amount=p.price,
                    bucket=STATUS_BUCKET.get(p.status, 'planned')))
    CashflowEntry.objects.filter(contract=contract).delete()
    CashflowEntry.objects.bulk_create(rows)
    return len(rows)
