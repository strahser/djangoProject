"""UI конвейера выдачи РД в ПР (M1 DOC-4, канон §6).

Очередь-канбан + карточка ревизии. Действия (validate/register/remarks/issue) —
те же эндпоинты /api/docs/ через fetch с CSRF (как тогглы в contract/dashboard).
Печать листа согласования и накладной — reportlab (образцы — сканы без слоя).
"""
from __future__ import annotations

import io
import os

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render

from .models import DocIssue, DocRegisterEntry, DocRemark, DocRevision
from .pdf_forms import remark_sheet_bytes, waybill_bytes

QUEUE_STATUSES = (
    ('received', 'Входящие'),
    ('validating', 'На проверке'),
    ('checked_ok', 'Проверены'),
    ('has_remarks', 'Замечания'),
    ('registered', 'К выдаче'),
    ('issued', 'Выдано'),
)


@login_required
def queue_view(request):
    q = (request.GET.get('q') or '').strip()
    columns = []
    for st, title in QUEUE_STATUSES:
        qs = (DocRevision.objects.filter(status=st)
              .select_related('entry', 'email').order_by('-received_at'))
        if q:
            qs = qs.filter(entry__cipher__icontains=q)
        columns.append({'status': st, 'title': title,
                        'count': qs.count(), 'items': list(qs[:50])})
    return render(request, 'DocRegistry/queue.html', {'columns': columns, 'q': q})


@login_required
def revision_view(request, pk):
    rev = get_object_or_404(
        DocRevision.objects.select_related('entry', 'email', 'attachment', 'task'), pk=pk)
    check = getattr(rev, 'validation', None)
    entry = rev.entry
    issues = list(entry.issues.all()) if entry else []
    logs = list((entry.changelog.all() if entry else DocRevision.objects.none())[:30])
    return render(request, 'DocRegistry/revision.html', {
        'rev': rev, 'check': check, 'entry': entry,
        'remarks': list(rev.remarks.all()), 'issues': issues, 'logs': logs,
    })


@login_required
def remark_sheet_pdf(request, pk):
    """Лист согласования по замечанию → PDF (сохраняется в remark.sheet_pdf)."""
    rm = get_object_or_404(DocRemark.objects.select_related('revision__entry'), pk=pk)
    pdf = remark_sheet_bytes(rm)
    rm.sheet_pdf.save(f'list-soglasovaniya-{rm.pk}.pdf', io.BytesIO(pdf), save=True)
    return FileResponse(io.BytesIO(pdf), content_type='application/pdf',
                        filename=f'list-soglasovaniya-{rm.pk}.pdf')


@login_required
def waybill_pdf(request, pk):
    """Накладная на передачу в ПР → PDF (сохраняется в issue.waybill_pdf)."""
    iss = get_object_or_404(DocIssue.objects.select_related('entry'), pk=pk)
    pdf = waybill_bytes(iss)
    iss.waybill_pdf.save(f'nakladnaya-{iss.waybill_no}.pdf', io.BytesIO(pdf), save=True)
    return FileResponse(io.BytesIO(pdf), content_type='application/pdf',
                        filename=f'nakladnaya-{iss.waybill_no}.pdf')


@login_required
def entry_view(request, code):
    entry = get_object_or_404(DocRegisterEntry, code=int(code))
    return render(request, 'DocRegistry/entry.html', {
        'entry': entry,
        'revisions': list(entry.revisions.select_related('email').order_by('rev_no')),
        'issues': list(entry.issues.all()),
        'logs': list(entry.changelog.all()[:30]),
    })
