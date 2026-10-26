# -*- coding: utf-8 -*-
"""P2: дашборд/памятка/cashflow ProjectContract (вынесено из views.py 1:1)."""
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render

from ProjectContract.models import Contractor
from StaticData.models import ProjectSite

from .models import Contract


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
