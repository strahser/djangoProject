import json

import pandas as pd
from django.http import JsonResponse
from django.http import HttpResponse
from django.db.models import Sum, Value, DecimalField, Q, F
from django.db.models.functions import Coalesce

from django_pandas.io import read_frame
from django.contrib import admin, messages
from loguru import logger

from AdminUtils import duplicate_object
from .admin import ContractAdmin
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import HttpResponseForbidden

from .form import ContractPaymentsForm
from .models import ContractPayments, Contract
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from StaticData.models import ProjectSite
from ProjectContract.models import Contractor


@login_required
def contract_dashboard(request):
    """Дашборд договоров: прогресс оплат, итоги, фильтры."""
    from ProjectContract.services import contract_totals
    contracts = Contract.objects.select_related(
        'project_site', 'contractor', 'client', 'parent'
    ).prefetch_related('contractpayments_set', 'children').order_by('project_site__name', 'name')

    q = (request.GET.get('q') or '').strip()
    project = request.GET.get('project') or ''
    contractor = request.GET.get('contractor') or ''
    if q:
        contracts = contracts.filter(name__icontains=q)
    if project:
        contracts = contracts.filter(project_site_id=project)
    if contractor:
        contracts = contracts.filter(contractor_id=contractor)

    rows, totals = [], {'price': 0, 'paid': 0, 'forecast': 0, 'planned': 0}
    for c in contracts:
        t = contract_totals(c)
        forecast = t['guaranteed'] + t['likely']
        rows.append({
            'contract': c, 'pays': list(c.contractpayments_set.all()),
            'paid': t['paid'], 'forecast': forecast, 'planned': t['planned'],
            'rest': (c.price or 0) - t['paid'] - forecast - t['planned'],
            'pct_paid': round(float(t['paid']) / float(c.price) * 100) if c.price else 0,
            'pct_guar': round(float(t['guaranteed']) / float(c.price) * 100) if c.price else 0,
            'pct_like': round(float(t['likely']) / float(c.price) * 100) if c.price else 0,
            'pct_plan': round(float(t['planned']) / float(c.price) * 100) if c.price else 0,
            'children': list(c.children.all()),
        })
        totals['price'] += c.price or 0
        totals['paid'] += t['paid']
        totals['forecast'] += forecast
        totals['planned'] += t['planned']

    return render(request, 'ProjectContract/dashboard.html', {
        'rows': rows, 'totals': totals,
        'projects': ProjectSite.objects.all().order_by('name'),
        'contractors': Contractor.objects.all().order_by('name'),
        'sel': {'q': q, 'project': project, 'contractor': contractor},
    })


@login_required
def help_memo(request):
    """Памятка «как устроены договоры/оплаты/ДДС» отдельной страницей."""
    return render(request, 'ProjectContract/help_memo.html')


CF_BUCKET_COLORS = {
    'fact': '#2ba55f',
    'guaranteed': '#2563eb',
    'likely': '#b45309',
    'planned': '#9aa3b2',
}


def _build_cashflow_chart(totals, bucket_names, periods, rows):
    """Собрать данные для Chart.js: stacked bars по корзинам + линия прогноза.

    Чистая функция — работает с уже агрегированными матрицами:
    totals[bucket][period], rows[..]['cells'][bucket][period].
    bucket_names — dict {code: name}. Возвращает dict, готовый к json.dumps.
    """
    keys = [p['key'] for p in periods]
    buckets = [
        {'code': b, 'name': bucket_names.get(b, b),
         'color': CF_BUCKET_COLORS.get(b, '#6c757d'),
         'values': [float((totals.get(b, {}) or {}).get(k) or 0) for k in keys]}
        for b in bucket_names
    ]
    gua = next((x for x in buckets if x['code'] == 'guaranteed'), None)
    lik = next((x for x in buckets if x['code'] == 'likely'), None)
    forecast = [
        round((gua['values'][i] if gua else 0) + (lik['values'][i] if lik else 0), 2)
        for i in range(len(keys))
    ]
    contracts = {}
    for row in rows:
        cells = row.get('cells', {}) or {}
        contracts[str(row.get('id'))] = {
            'name': row['name'],
            'buckets': {
                b: [float((cells.get(b, {}) or {}).get(k) or 0) for k in keys]
                for b in bucket_names
            },
        }
    return {
        'labels': [p['label'] for p in periods],
        'buckets': buckets,
        'forecast': forecast,
        'contracts': contracts,
    }


@login_required
def cashflow(request):
    """ДДС из материализованных строк: факт + прогноз по периодам (Ф2).

    Чтение — одна SQL-агрегация, без pandas. Пересчёт строк — сигнал
    save/delete платежа или команда rebuild_cashflow.
    """
    from django.db.models.functions import TruncDay, TruncMonth, TruncQuarter, TruncWeek
    from ProjectContract.models import CashflowEntry
    scale = request.GET.get('scale', 'month')
    trunc = {'day': TruncDay, 'week': TruncWeek,
             'month': TruncMonth, 'quarter': TruncQuarter}.get(scale, TruncMonth)
    if scale not in ('day', 'week', 'month', 'quarter'):
        scale = 'month'

    agg = (CashflowEntry.objects
           .annotate(period=trunc('date'))
           .values('contract_id', 'contract__name', 'bucket', 'period')
           .annotate(total=Sum('amount'))
           .order_by('contract__name', 'period'))

    def label(dt):
        if scale == 'day':
            return dt.strftime('%d.%m.%y')
        if scale == 'week':
            return 'нед ' + dt.strftime('%d.%m')
        if scale == 'quarter':
            return f'К{(dt.month - 1) // 3 + 1}.{dt.year}'
        return dt.strftime('%m.%Y')

    period_keys = sorted({r['period'] for r in agg})
    periods = [{'key': p, 'label': label(p)} for p in period_keys]
    buckets = CashflowEntry.BUCKETS

    table = {}
    for r in agg:
        row = table.setdefault(r['contract_id'],
                               {'id': r['contract_id'], 'name': r['contract__name'], 'cells': {}})
        row['cells'].setdefault(r['bucket'], {})[r['period']] = r['total']
    rows = [table[k] for k in sorted(table, key=lambda k: table[k]['name'])]

    totals = {b[0]: {p['key']: 0 for p in periods} for b in buckets}
    for row in rows:
        for b, cells in row['cells'].items():
            for p, v in cells.items():
                totals[b][p] += v

    chart_data = _build_cashflow_chart(
        totals, dict(buckets), periods, rows)

    return render(request, 'ProjectContract/cashflow.html', {
        'scale': scale, 'periods': periods, 'buckets': buckets,
        'rows': rows, 'totals': totals, 'chart_data': json.dumps(chart_data),
    })


@login_required
@require_POST
def toggle_payment(request, pk):
    """Быстрое переключение статуса оплаты платежа (paid <-> planned).

    Статус — источник истины; флаг made_payment синхронизируется в save().
    """
    from django.utils import timezone
    from ProjectContract.services import log_change
    p = get_object_or_404(ContractPayments, pk=pk)
    old_status = p.status
    p.status = 'planned' if p.status == 'paid' else 'paid'
    if p.status == 'paid' and p.paid_date is None:
        p.paid_date = timezone.now().date()
    p.save()
    log_change(payment=p, action='paid' if p.status == 'paid' else 'unpaid',
               details=f'{old_status} → {p.status}: {p.name} ({p.price})',
               user=request.user)
    return JsonResponse({'ok': True, 'made': p.made_payment, 'price': float(p.price or 0)})


def duplicate_contractpayment(request, pk):
    payment = get_object_or_404(ContractPayments, pk=pk)
    duplicate_object(payment)  # Вызываем функцию дублирования
    return redirect(request.META.get('HTTP_REFERER', reverse(
        'admin:ProjectContract_contract_change', # Замените your_app на ваше приложение
         args=[payment.contract.pk]))
        )

def payments_gantt(request):
    payments = ContractPayments.objects.all()

    # Подготовка данных для jQuery.Gantt в формате JSON
    gantt_data = []
    for payment in payments:
        if not (payment.start_date and payment.due_date):
            continue
        gantt_data.append({
            "id": payment.id,
            "name": payment.name,
            "start": payment.start_date.strftime('%Y-%m-%d'),
            "end": payment.due_date.strftime('%Y-%m-%d'),
            "progress": 100 if payment.made_payment else 0,
            "parent": payment.parent_id if payment.parent else None,
            "sort_order": payment.id,  # Добавляем поле sort_order
            "dependencies": [payment.parent_id] if payment.parent else [],  # Добавляем зависимости
        })

    # Передача данных в шаблон
    context = {"gantt_data": json.dumps(gantt_data)}
    return render(request, 'ProjectContract/gantt_chart.html', context)


def data(request):
    payments = ContractPayments.objects.all()

    # Подготовка данных для jQuery.Gantt в формате JSON
    gantt_data = []
    for payment in payments:
        if not (payment.start_date and payment.due_date):
            continue
        gantt_data.append({
            "id": payment.id,
            "name": payment.name,
            "start": payment.start_date.strftime('%Y-%m-%d'),
            "end": payment.due_date.strftime('%Y-%m-%d'),
            "progress": 100 if payment.made_payment else 0,
            "parent": payment.parent_id if payment.parent else None,
            "sort_order": payment.id,  # Добавляем поле sort_order
            "dependencies": [payment.parent_id] if payment.parent else [],  # Добавляем зависимости
        })

    return JsonResponse(gantt_data, safe=False)


def export_contracts_excel(request):
    """
   Представление для экспорта отфильтрованных контрактов в Excel.
   """

    # Получаем queryset на основе текущих фильтров
    queryset = Contract.objects.all()
    # Вытаскиваем параметры из GET запроса и применяем фильтр, как в админке
    filter_params = {}
    for key, value in request.GET.items():
        if key not in ['csrfmiddlewaretoken', '_changelist_filters', 'scale', 'e']:  # отбрасываем токен, фильтр и служебные
            filter_params[key] = value

    if filter_params:
        queryset = queryset.filter(**filter_params)

    # Получаем отображаемые поля из list_display (как в ContractAdmin)

    modeladmin = ContractAdmin(Contract, admin.site)
    list_display = [val for val in modeladmin.list_display if val!= 'actions_column']

    # Аннотируем queryset нужными полями
    queryset = queryset.annotate(
        paid_amount=Coalesce(Sum('contractpayments__price', filter=Q(contractpayments__made_payment=True)), Value(0),
                             output_field=DecimalField(max_digits=12, decimal_places=2))
    ).annotate(
        unpaid_amount=Coalesce(Sum('contractpayments__price', filter=Q(contractpayments__made_payment=False)), Value(0),
                               output_field=DecimalField(max_digits=12, decimal_places=2))
    ).annotate(
        status_check=F('price') - (
                    Coalesce(Sum('contractpayments__price', filter=Q(contractpayments__made_payment=True)), Value(0),
                             output_field=DecimalField(max_digits=12, decimal_places=2)) + Coalesce(
                Sum('contractpayments__price', filter=Q(contractpayments__made_payment=False)), Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2)))
    )

    # Получаем verbose_name для полей
    verbose_names = {}
    for field_name in list_display:
        if hasattr(modeladmin, field_name):  # проверяем, если это функция, а не поле
            verbose_names[field_name] = getattr(modeladmin, field_name).short_description
        else:
            verbose_names[field_name] = modeladmin.model._meta.get_field(field_name).verbose_name

    # Создаем DataFrame, используя django-pandas
    df = read_frame(
        queryset,
        fieldnames=list_display,
    )

    # Конвертируем Decimal и другие типы в float перед экспортом
    for column in df.columns:
        if df[column].dtype == 'object':
            try:
                df[column] = df[column].astype(float)
            except (ValueError, TypeError):
                pass  # Оставляем как есть, если не удается преобразовать
    # Переименовываем столбцы
    df.rename(columns=verbose_names, inplace=True)

    # Создаем HTTP-ответ с Excel-файлом
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Контракты.xlsx"'
    writer = pd.ExcelWriter(response, engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Задачи', index=False, freeze_panes=(1, 1))
    workbook = writer.book
    worksheet = writer.sheets['Задачи']
    column_settings = [{'header': column} for column in df]
    (max_row, max_col) = df.shape
    worksheet.add_table(0, 0, max_row, max_col - 1,
                        {'columns': column_settings,
                         'banded_columns': True,
                         'autofilter': True,
                         'name': 'Задачи',
                         'style': 'Table Style Light 8'})
    writer.close()
    return response


def contract_payment_delete(request, payment_id):
    """
    View для удаления ContractPayments.
    """
    if not request.user.is_staff:
        return HttpResponseForbidden("Доступ запрещен")

    payment = get_object_or_404(ContractPayments, pk=payment_id)
    contract_id = payment.contract_id

    if request.method == "POST":
        payment.delete()
        _next = request.GET.get('_next')
        if _next:
            return redirect(_next)
        else:
            return redirect(reverse('admin:ProjectContract_contract_change', args=[contract_id]))

    return render(request, 'admin/contract_payments_delete.html', {
        'payment': payment,
        'is_popup': True,
        'title': 'Удаление платежа'
    })


def contract_payment_add_edit(request, contract_id=None, payment_id=None):
    """
    View для отображения формы создания/редактирования ContractPayments в модальном окне.
    """
    if not request.user.is_staff:
        return HttpResponseForbidden("Доступ запрещен")

    contract = None
    payment = None

    if contract_id:
        contract = get_object_or_404(Contract, pk=contract_id)

    if payment_id:
        payment = get_object_or_404(ContractPayments, pk=payment_id)

    if request.method == "POST":
        form = ContractPaymentsForm(request.POST, instance=payment)
        if form.is_valid():
            new_payment = form.save(commit=False)
            if contract:
                new_payment.contract = contract
            new_payment.save()

            _next = request.GET.get('_next')
            if _next:
                return redirect(_next)
            else:
                return redirect(reverse('admin:ProjectContract_contract_change',
                                        args=[contract.pk if contract else payment.contract.pk]))
    else:
        form = ContractPaymentsForm(instance=payment, initial={'contract': contract})

    return render(request, 'admin/contract_payments_form.html', {
        'form': form,
        'contract': contract,
        'payment': payment,
        'is_popup': True,
        'title': 'Редактирование платежа' if payment else 'Добавить платеж',
    })


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