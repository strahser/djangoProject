# -*- coding: utf-8 -*-
"""P2: платежи ProjectContract — тогглы, гант, экспорт, CRUD (вынесено из views.py 1:1)."""
import json

import pandas as pd
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, F, Q, Sum, Value
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django_pandas.io import read_frame

from AdminUtils import duplicate_object

from .admin import ContractAdmin
from .form import ContractPaymentsForm
from .models import Contract, ContractPayments


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
