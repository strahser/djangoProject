"""API конвейера РД для ИИ-агента (канон §5).

Один объект — один реестр: все маршруты несут код объекта (M1/K1),
каждый работает строго со своими таблицами (см. REGISTRIES).
Агент ходит только сюда, не в БД напрямую. Каждый POST пишет журнал source='api'.
Валидация выполняется движком DesignBase (DESIGNBASE_URL); при его недоступности — 503.
"""
from __future__ import annotations

import hashlib
import os

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from Emails.models import Email

from . import designbase_client as dbc
from .models import get_registry_or_404
from .serializers import entry_serializer_for, revision_serializer_for
from .services import next_code

QUEUE_STATUSES = ('received', 'validating', 'checked_ok', 'has_remarks', 'registered')
QUEUE_LIMIT = 100


def _log(ChangeLog, *, entry=None, revision=None, field, old='', new='', user=None):
    ChangeLog.objects.create(
        entry=entry, revision=revision, field=field,
        old_value=str(old)[:2000], new_value=str(new)[:2000],
        changed_by=user if user and user.is_authenticated else None,
        source='api',
    )


def _file_fingerprint(path: str) -> tuple[str, int]:
    """sha256 + размер файла с диска; нет файла — ('', 0)."""
    if not path or not os.path.isfile(path):
        return '', 0
    h = hashlib.sha256()
    size = 0
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def intake(request, project):
    """Шаг 1: приём вложений письма → ревизия(received) в реестре объекта.
    Тело: {email_id, attachment_id?}."""
    R = get_registry_or_404(project)
    email = get_object_or_404(Email, pk=request.data.get('email_id'))
    atts = list(email.attachments.all().order_by('id'))
    att = None
    if request.data.get('attachment_id'):
        att = get_object_or_404(email.attachments.all(), pk=request.data['attachment_id'])
    else:
        att = next((a for a in atts if not a.is_inline), atts[0] if atts else None)
    sha, size = _file_fingerprint(att.file_path if att else '')
    rev = R['revision'].objects.create(
        entry=None, email=email, attachment=att, source='email',
        sha256=sha, size=size, status='received',
    )
    _log(R['changelog'], revision=rev, field='intake', old='',
         new=f'email={email.pk} att={att.pk if att else None}', user=request.user)
    return Response(revision_serializer_for(R['revision'])(rev).data,
                    status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate(request, project, rev_id):
    """Шаг 2: валидация движком DesignBase → проверка + статус checked_ok/has_remarks.

    FAIL если Подано.verdict == NO_CODE (работа не подана — канон П2).
    """
    R = get_registry_or_404(project)
    rev = get_object_or_404(R['revision'], pk=rev_id)
    if rev.status not in ('received', 'validating', 'has_remarks', 'checked_ok'):
        return Response({'error': f'статус {rev.status} не валидируется'}, status=400)
    old_status = rev.status
    rev.status = 'validating'
    rev.save(update_fields=['status'])

    file_path = rev.attachment.file_path if rev.attachment else ''
    prev = R['revision'].objects.filter(
        entry=rev.entry, rev_no__lt=rev.rev_no).exclude(entry=None).order_by('-rev_no').first()
    prev_path = (prev.attachment.file_path if prev and prev.attachment else '') or ''
    checks: dict = {}
    try:
        if file_path and prev_path and os.path.isfile(file_path) and os.path.isfile(prev_path):
            checks['diff'] = dbc.post('/validate/diff', {'old_path': prev_path, 'new_path': file_path})
        else:
            checks['diff'] = {'hint': 'SKIPPED', 'reason': 'нет пары файлов для diff'}
        if file_path and os.path.isfile(file_path):
            checks['pechat'] = dbc.get('/validate/pechat', {
                'filename': os.path.basename(file_path), 'size': rev.size or 0})
        # код-кандидат можно подсказать до register: {"code": N}
        code = rev.entry.code if rev.entry else request.data.get('code')
        code = int(code) if code else None
        if code:
            checks['podano'] = dbc.get('/validate/podano', {'code': code})
        cipher = rev.entry.cipher if rev.entry else None
        if code and not cipher:
            cipher = R['entry'].objects.filter(code=code).values_list('cipher', flat=True).first()
        if cipher:
            checks['dds'] = dbc.get('/validate/dds', {'cipher': cipher})
    except dbc.DesignBaseUnreachable as e:
        rev.status = old_status
        rev.save(update_fields=['status'])
        return Response({'error': f'DesignBase недоступен: {e}'}, status=503)

    questions: list[str] = []
    pod = checks.get('podano') or {}
    if pod.get('verdict') == 'NO_CODE':
        questions.append(f'Код {code} отсутствует в accdb — работа не подана, закрывать нельзя (канон П2).')
    elif pod.get('verdict') == 'NO_FOLDER':
        questions.append(f'Нет папки Подано\\2026\\{pod.get("row", {}).get("Дата подачи на согласование", "?")[:10]}_* — подать + номер в реестр (канон П2).')
    if (checks.get('pechat') or {}).get('found') is False and (checks.get('diff') or {}).get('hint') not in ('SKIPPED',):
        questions.append('Файла нет в Печати — подтвердить место и шифр до выдачи (канон §4 вопрос 3).')

    verdict = 'FAIL' if pod.get('verdict') == 'NO_CODE' else 'PASS'
    R['check'].objects.update_or_create(
        revision=rev,
        defaults={'verdict': verdict, 'diff_json': checks.get('diff', {}),
                  'checks_json': {k: v for k, v in checks.items() if k != 'diff'},
                  'questions_md': '\n'.join(f'{i + 1}. {q}' for i, q in enumerate(questions)),
                  'checked_by': request.user if request.user.is_authenticated else None},
    )
    rev.status = 'checked_ok' if verdict == 'PASS' else 'has_remarks'
    rev.save(update_fields=['status'])
    _log(R['changelog'], entry=rev.entry, revision=rev, field='validate', old=old_status,
         new=f'{rev.status} ({verdict})', user=request.user)
    return Response({'revision': rev.pk, 'project': project, 'status': rev.status,
                     'verdict': verdict, 'questions': questions, 'checks': checks})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register(request, project, rev_id):
    """Шаг 3: запись в реестр объекта. Тело: {code?} — существующий код либо новый (confirm при новом шифре)."""
    R = get_registry_or_404(project)
    rev = get_object_or_404(R['revision'], pk=rev_id)
    check = getattr(rev, 'validation', None)
    if not check or check.verdict != 'PASS':
        return Response({'error': 'нужен DocCheck PASS (шаг 2)'}, status=400)
    code = request.data.get('code')
    confirm = request.data.get('confirm') is True
    if code:
        entry = get_object_or_404(R['entry'], code=int(code))
    elif rev.entry:
        entry = rev.entry
    else:
        if not confirm:
            return Response({'error': 'новая запись реестра — нужен confirm:true',
                             'project': project,
                             'next_code': next_code(R['entry'])}, status=400)
        entry = R['entry'].objects.create(code=next_code(R['entry']))
    if rev.entry_id != entry.pk:
        old = rev.entry.code if rev.entry else None
        rev.entry = entry
        rev.save(update_fields=['entry'])
        _log(R['changelog'], entry=entry, revision=rev, field='entry', old=old, new=entry.code,
             user=request.user)
    # номер ревизии в рамках записи
    if rev.rev_no <= 0:
        rev.rev_no = 1
    last = R['revision'].objects.filter(entry=entry).exclude(pk=rev.pk).order_by('-rev_no').first()
    if last and rev.rev_no <= last.rev_no:
        rev.rev_no = last.rev_no + 1
        rev.save(update_fields=['rev_no'])
    rev.status = 'registered'
    rev.save(update_fields=['status'])
    _log(R['changelog'], entry=entry, revision=rev, field='register', old='', new=entry.code,
         user=request.user)
    return Response({'revision': rev.pk, 'entry': entry.code, 'project': project,
                     'rev_no': rev.rev_no, 'status': rev.status})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def remarks(request, project, rev_id):
    """Шаг 4а: замечание + (позже) лист согласования. Тело: {text}."""
    R = get_registry_or_404(project)
    rev = get_object_or_404(R['revision'], pk=rev_id)
    text = (request.data.get('text') or '').strip()
    if not text:
        return Response({'error': 'нужен text'}, status=400)
    rm = R['remark'].objects.create(revision=rev, text=text)
    old = rev.status
    rev.status = 'has_remarks'
    rev.save(update_fields=['status'])
    _log(R['changelog'], entry=rev.entry, revision=rev, field='remarks', old=old, new=f'#{rm.pk}',
         user=request.user)
    return Response({'remark': rm.pk, 'status': rev.status}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def issue(request, project, rev_id):
    """Шаг 4б–5: выдача в ПР. Тело: {waybill_no, waybill_date?, network_path?}."""
    R = get_registry_or_404(project)
    rev = get_object_or_404(R['revision'], pk=rev_id)
    if rev.status != 'registered':
        return Response({'error': 'выдача только из статуса registered (шаг 3)'}, status=400)
    if not rev.entry:
        return Response({'error': 'нет записи реестра'}, status=400)
    no = (request.data.get('waybill_no') or '').strip()
    if not no:
        return Response({'error': 'нужен waybill_no'}, status=400)
    iss = R['issue'].objects.create(
        entry=rev.entry, waybill_no=no,
        waybill_date=request.data.get('waybill_date') or None,
        network_path=request.data.get('network_path') or '',
        issued_by=request.user if request.user.is_authenticated else None,
    )
    rev.status = 'issued'
    rev.save(update_fields=['status'])
    _log(R['changelog'], entry=rev.entry, revision=rev, field='issue', old='registered', new=no,
         user=request.user)
    return Response({'issue': iss.pk, 'status': rev.status}, status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def queue(request, project):
    """Очередь конвейера объекта по статусам для агента."""
    R = get_registry_or_404(project)
    out = {}
    for st in QUEUE_STATUSES:
        qs = (R['revision'].objects.filter(status=st)
              .select_related('entry', 'email').order_by('-received_at')[:QUEUE_LIMIT])
        out[st] = [{
            'id': r.pk, 'entry': r.entry.code if r.entry else None,
            'cipher': r.entry.cipher if r.entry else '',
            'rev_no': r.rev_no, 'email': r.email_id,
            'file': r.attachment.filename if r.attachment else '',
            'received_at': r.received_at.isoformat() if r.received_at else None,
        } for r in qs]
    out['counts'] = {k: len(v) for k, v in out.items()}
    return Response(out)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def entry_card(request, project, code):
    """Карточка записи реестра объекта: ревизии, проверки, замечания, выдачи, связи."""
    R = get_registry_or_404(project)
    entry = get_object_or_404(R['entry'], code=int(code))
    revs = []
    for r in entry.revisions.select_related('email', 'task').order_by('rev_no'):
        chk = getattr(r, 'validation', None)
        revs.append({
            'id': r.pk, 'rev_no': r.rev_no, 'status': r.status, 'source': r.source,
            'size': r.size, 'sha256': r.sha256[:16],
            'email': r.email_id, 'task': r.task_id,
            'check': chk.verdict if chk else None,
            'questions': (chk.questions_md if chk else ''),
            'remarks': r.remarks.count(),
        })
    issues = [{'id': i.pk, 'waybill_no': i.waybill_no,
               'waybill_date': i.waybill_date.isoformat() if i.waybill_date else None,
               'network_path': i.network_path, 'archived_old_rev': i.archived_old_rev}
              for i in entry.issues.all()]
    logs = [{'field': l.field, 'old': l.old_value, 'new': l.new_value,
             'source': l.source, 'at': l.changed_at.isoformat() if l.changed_at else None}
            for l in entry.changelog.all()[:20]]
    data = entry_serializer_for(R['entry'])(entry).data
    data.update({'revisions': revs, 'issues': issues, 'changelog': logs})
    return Response(data)
