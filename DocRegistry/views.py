"""UI конвейера выдачи РД в ПР (канон §6).

Один объект — один реестр: все страницы несут код объекта (M1/K1).
Очередь-канбан + карточка ревизии. Действия (validate/register/remarks/issue) —
те же эндпоинты /api/docs/<project>/ через fetch с CSRF.
Печать листа согласования и накладной — reportlab.
"""
from __future__ import annotations

import io

from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404, render

from .models import get_registry_or_404
from .pdf_forms import approval_sheet_bytes, remark_sheet_bytes, waybill_bytes
from .services import signers_for

QUEUE_STATUSES = (
    ('received', 'Входящие'),
    ('validating', 'На проверке'),
    ('checked_ok', 'Проверены'),
    ('has_remarks', 'Замечания'),
    ('registered', 'К выдаче'),
    ('issued', 'Выдано'),
)


@login_required
def queue_view(request, project):
    R = get_registry_or_404(project)
    q = (request.GET.get('q') or '').strip()
    columns = []
    for st, title in QUEUE_STATUSES:
        qs = (R['revision'].objects.filter(status=st)
              .select_related('entry', 'email').order_by('-received_at'))
        if q:
            qs = qs.filter(entry__cipher__icontains=q)
        columns.append({'status': st, 'title': title,
                        'count': qs.count(), 'items': list(qs[:50])})
    return render(request, 'DocRegistry/queue.html',
                  {'columns': columns, 'q': q, 'project': project})


@login_required
def revision_view(request, project, pk):
    R = get_registry_or_404(project)
    rev = get_object_or_404(
        R['revision'].objects.select_related('entry', 'email', 'attachment', 'task'), pk=pk)
    check = getattr(rev, 'validation', None)
    entry = rev.entry
    issues = list(entry.issues.all()) if entry else []
    logs = list((entry.changelog.all() if entry else R['revision'].objects.none())[:30])
    return render(request, 'DocRegistry/revision.html', {
        'rev': rev, 'check': check, 'entry': entry, 'project': project,
        'remarks': list(rev.remarks.all()), 'issues': issues, 'logs': logs,
    })


@login_required
def remark_sheet_pdf(request, project, pk):
    """Лист согласования по замечанию → PDF (сохраняется в remark.sheet_pdf)."""
    R = get_registry_or_404(project)
    rm = get_object_or_404(R['remark'].objects.select_related('revision__entry'), pk=pk)
    pdf = remark_sheet_bytes(rm)
    rm.sheet_pdf.save(f'list-soglasovaniya-{rm.pk}.pdf', io.BytesIO(pdf), save=True)
    return FileResponse(io.BytesIO(pdf), content_type='application/pdf',
                        filename=f'list-soglasovaniya-{rm.pk}.pdf')


@login_required
def waybill_pdf(request, project, pk):
    """Накладная на передачу в ПР → PDF (сохраняется в issue.waybill_pdf)."""
    R = get_registry_or_404(project)
    iss = get_object_or_404(R['issue'].objects.select_related('entry'), pk=pk)
    pdf = waybill_bytes(iss)
    iss.waybill_pdf.save(f'nakladnaya-{iss.waybill_no}.pdf', io.BytesIO(pdf), save=True)
    return FileResponse(io.BytesIO(pdf), content_type='application/pdf',
                        filename=f'nakladnaya-{iss.waybill_no}.pdf')


@login_required
def approval_pdf(request, project, pk):
    """Лист согласования в ПР по образцу (подписанты — общие) → PDF."""
    R = get_registry_or_404(project)
    iss = get_object_or_404(
        R['issue'].objects.select_related('entry__building', 'entry__developer'), pk=pk)
    pdf = approval_sheet_bytes(iss, signers_for())
    iss.approval_pdf.save(f'list-soglasovaniya-{iss.entry.code}.pdf', io.BytesIO(pdf), save=True)
    return FileResponse(io.BytesIO(pdf), content_type='application/pdf',
                        filename=f'list-soglasovaniya-{iss.entry.code}.pdf')


@login_required
def entry_view(request, project, code):
    R = get_registry_or_404(project)
    entry = get_object_or_404(R['entry'], code=int(code))
    return render(request, 'DocRegistry/entry.html', {
        'entry': entry, 'project': project,
        'revisions': list(entry.revisions.select_related('email').order_by('rev_no')),
        'issues': list(entry.issues.all()),
        'logs': list(entry.changelog.all()[:30]),
    })
