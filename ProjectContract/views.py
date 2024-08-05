from django.shortcuts import render

from ProjectContract.models import ContractPayments
import json
from django.http import JsonResponse


def payments_gantt(request):
    payments = ContractPayments.objects.all()

    # Подготовка данных для jQuery.Gantt в формате JSON
    gantt_data = []
    for payment in payments:
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
