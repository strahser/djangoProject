import json
import mimetypes
import os
import subprocess
from sys import platform

from django.contrib import messages
from django.contrib.admin.utils import flatten
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.functions import Coalesce, TruncDate
from django.http import (
    FileResponse, Http404, HttpResponse, HttpResponseBadRequest, JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from loguru import logger

from Emails.models import Attachment, Email, EmailType, InfoChoices
from Emails.ЕmailParser.EmailConfig import E_MAIL_DIRECTORY
from Emails.ЕmailParser.ParsingImapEmailToDB import ParsingImapEmailToDB
from ProjectContract.models import Contractor
from ProjectTDL.models import TaskNode
from StaticData.models import BuildingType, Category, ProjectSite, Status

from .forms import (
    ComposeEmailForm, ComposeReplyForm, ContactEmailForm, ContactForm,
    ContactGroupForm, EmailFilterForm, EmailMetadataForm, EmailRuleForm, EmailTagForm,
    ExportForm, SavedFilterForm, TaskSearchForm,
)
from .models import (
    Contact, ContactEmail, ContactGroup, EmailAutomationLog, EmailEmailTag, EmailRule,
    EmailTag, EmailTaskLink, EmailTemplate, EmailViewSettings, SavedFilter, SMTPAccount,
)
from .services.email_sender import EmailSenderService
from .utils import (
    clean_email_html, extract_email_address, extract_all_email_addresses, resolve_sender_to_email,
    resolve_inline_image_urls, sanitize_id, sanitize_id_list, segment_letter_html,
)
PER_PAGE = 50
THREADS_PER_PAGE = 20
ALLOWED_SORT_FIELDS = ['sender', 'receiver', 'subject', 'email_stamp', 'project_site__name', 'contractor__name']


def _contacts_picker_json(contacts):
    """Единый источник данных пикера контактов: список [{n: имя, e: email}].

    Возвращает Python-список — сериализует шаблонный фильтр json_script.
    """
    from .utils import canonical_email
    out, seen = [], set()
    for c in contacts:
        try:
            primary = c.primary_email
            raw = (primary.email if primary else '').strip()
        except Exception:
            raw = ''
        addr = canonical_email(raw) or raw
        if addr and addr.lower() not in seen:
            seen.add(addr.lower())
            out.append({'n': c.name or '', 'e': addr})
    return out


def _attach_thread_context(emails, head_cache=None, with_head=True):
    """Досчитывает поля для режима цепочек: direction in/out, body_head.

    Мутирует объекты (атрибуты, не колонки БД). head_cache — dict на запрос,
    чтобы не читать один HTML-файл дважды. with_head=False — только direction
    (дешёво, без чтения файлов: для подсчёта Вх./Исх. до пагинации).
    """
    from .utils import email_body_head
    if head_cache is None:
        head_cache = {}
    for email in emails:
        email.direction = (
            'out' if (email.email_type or '').upper() == 'OUT' else 'in'
        )
        email.direction_label = 'Исходящее' if email.direction == 'out' else 'Входящее'
        if with_head and not getattr(email, 'body_head', ''):
            try:
                email.body_head = email_body_head(email, 220, head_cache)
            except Exception:
                email.body_head = ''
        elif not hasattr(email, 'body_head'):
            email.body_head = ''


def _build_thread_list(emails):
    """Группирует письма в цепочки по теме (ThreadService), сортирует по свежим.

    Возвращает список dict: key/subject/emails/count/in_count/out_count/earliest/latest.
    Письма внутри — хронологически (старые сверху, как чтение переписки).
    """
    from .services.thread_service import ThreadService
    threads = ThreadService.build_threads(emails)
    out = []
    for key, msgs in threads.items():
        # Только direction (без чтения файлов) — головы дочитаем после пагинации.
        _attach_thread_context(msgs, with_head=False)
        latest = max(
            (m.email_stamp or m.creation_stamp for m in msgs if m.email_stamp or m.creation_stamp),
            default=None,
        )
        earliest = min(
            (m.email_stamp or m.creation_stamp for m in msgs if m.email_stamp or m.creation_stamp),
            default=None,
        )
        # Тема для заголовка — из самого свежего письма (сохраняет Re:/Fwd:).
        subj_src = max(msgs, key=lambda m: (m.email_stamp or m.creation_stamp or m.id))
        out.append({
            'key': key,
            'subject': (subj_src.subject or '').strip() or 'Без темы',
            'emails': msgs,
            'count': len(msgs),
            'in_count': sum(1 for m in msgs if m.direction == 'in'),
            'out_count': sum(1 for m in msgs if m.direction == 'out'),
            'earliest': earliest,
            'latest': latest,
        })
    def _thread_ts(t):
        dt = t['latest']
        try:
            return dt.timestamp() if dt else float('-inf')
        except Exception:
            return float('-inf')
    out.sort(key=_thread_ts, reverse=True)
    return out


def _attach_thread_page_heads(thread_page):
    """Дочитывает body_head только для писем текущей страницы цепочек."""
    head_cache = {}
    for t in thread_page:
        _attach_thread_context(t['emails'], head_cache, with_head=True)


def _build_selection_threads(selected_ids):
    """Цепочки для выбранных писем: сами письма + связанные из inbox+sent.

    Связь — общий thread_id или одинаковая нормализованная тема
    (ThreadService.normalize_subject: режутся Re:/Fwd: и т.п.).
    Выбранные включаются всегда, даже из других папок.
    """
    from .services.thread_service import ThreadService
    sel = list(Email.objects.filter(pk__in=selected_ids))
    if not sel:
        return []
    norms, tids = set(), set()
    for e in sel:
        n = ThreadService.normalize_subject(e.subject or '')
        if n:
            norms.add(n)
        tid = (e.thread_id or '').strip()
        if tid:
            tids.add(tid)
    matched = {e.pk for e in sel}
    if norms or tids:
        rows = Email.objects.filter(folder__in=('inbox', 'sent')).values(
            'id', 'subject', 'thread_id')
        for r in rows:
            rtid = (r['thread_id'] or '').strip()
            if rtid and rtid in tids:
                matched.add(r['id'])
                continue
            if norms and ThreadService.normalize_subject(r['subject'] or '') in norms:
                matched.add(r['id'])
    emails = list(
        Email.objects.filter(pk__in=matched).select_related(
            'project_site', 'contractor', 'category', 'building_type',
        ).prefetch_related('attachments'))
    thread_list = _build_thread_list(emails)
    _attach_thread_page_heads(thread_list)
    return thread_list


@login_required
@require_http_methods(['POST'])
def selection_threads(request):
    """Цепочки выбранных писем (контекстный фильтр bulk-панели).

    Принимает те же поля, что bulk_action: selected_emails / select_all +
    filter_params + folder. Рендерит цепочки в #email-list-container;
    обратно — кнопка «К списку» (back_url из исходных параметров фильтра).
    """
    folder = request.POST.get('folder', 'inbox')
    filter_params = request.POST.get('filter_params', '')
    if request.POST.get('select_all') == '1':
        emails = Email.objects.filter(folder=folder)
        if filter_params:
            from django.http import QueryDict
            filter_form = EmailFilterForm(QueryDict(filter_params))
            if filter_form.is_valid():
                emails = filter_emails(emails, filter_form.cleaned_data)
        selected_ids = list(emails.values_list('id', flat=True))
    else:
        selected_ids = sanitize_id_list(request.POST.getlist('selected_emails'))
    if not selected_ids:
        return HttpResponseBadRequest('Нет выбранных писем')
    thread_list = _build_selection_threads(selected_ids)
    # Одна страница (контекстный просмотр целиком), пейджер скрыт.
    thread_page = Paginator(thread_list, max(len(thread_list), 1)).get_page(1)

    from django.http import QueryDict
    back_qd = QueryDict(filter_params, mutable=True)
    back_qd['folder'] = folder
    back_url = reverse('email_ui:email_list_partial') + '?' + back_qd.urlencode()
    context = {
        'selection_mode': True,
        'selected_count': len(selected_ids),
        'thread_page': thread_page,
        'thread_total': len(thread_list),
        'email_list_back_url': back_url,
        'back_url': back_url,
    }
    return render(request, 'email_ui/partials/email_threads.html', context)


def _sanitize_next_url(next_url):
    """Ensure 'next' always points to a full page, not a partial/ URL."""
    from django.http import QueryDict
    if not next_url:
        return reverse('email_ui:inbox_default')
    # Защита от open-redirect: разрешаем только локальные пути.
    if not next_url.startswith('/'):
        return reverse('email_ui:inbox_default')
    if '/partial/' in next_url:
        try:
            folder = 'inbox'
            qd = QueryDict('')
            if '?' in next_url:
                qs = next_url.split('?', 1)[1]
                qd = QueryDict(qs)
                folder = qd.get('folder', 'inbox')
            url = reverse('email_ui:inbox', args=[folder])
            qd_copy = qd.copy()
            for key in ('sort', 'order', 'folder'):
                qd_copy.pop(key, None)
            qs2 = qd_copy.urlencode()
            if qs2:
                url += '?' + qs2
            return url
        except Exception:
            return reverse('email_ui:inbox_default')
    return next_url


def _clean_query_string(request, remove_params=None):
    """Remove specified params from query string and return URL-encoded string."""
    if remove_params is None:
        remove_params = ['sort', 'order']
    params = request.GET.copy()
    for key in remove_params:
        params.pop(key, None)
    return params.urlencode()


def _build_back_url(request, folder='inbox'):
    """Build a full-page back URL for email list, avoiding /partial/ paths."""
    qs = _clean_query_string(request, remove_params=['sort', 'order', 'folder'])
    url = reverse('email_ui:inbox', args=[folder])
    if qs:
        url += '?' + qs
    return url


def apply_sorting(queryset, request):
    sort_field = request.GET.get('sort', 'email_stamp')
    sort_order = request.GET.get('order', 'desc')

    if sort_field.lstrip('-') not in ALLOWED_SORT_FIELDS:
        sort_field = 'email_stamp'

    if sort_order == 'desc' and not sort_field.startswith('-'):
        sort_field = f'-{sort_field}'

    return queryset.order_by(sort_field), sort_field.lstrip('-'), sort_order


def _split_tokens(raw):
    """Делит мульти-ввод почты на токены (запятая/точка с запятой)."""
    if not raw:
        return []
    return [t.strip() for t in str(raw).replace(';', ',').split(',') if t.strip()]


# Поля общего поиска («везде»): тема + все адресные поля + наименование.
SEARCH_ANYWHERE_FIELDS = (
    'subject', 'sender', 'sender_name', 'receiver', 'cc', 'bcc', 'name',
)


def _ci_variants(token):
    """Варианты регистра для токена.

    SQLite LIKE (а значит и Django __icontains) регистронезависим только
    для ASCII. Для кириллицы 'совещание' не найдёт 'Совещание' и наоборот.
    Поэтому ищем сразу по нескольким вариантам через ИЛИ.
    """
    t = (token or '').strip()
    if not t:
        return []
    variants = {t, t.lower(), t.upper(), t.capitalize(), t.title()}
    return [v for v in variants if v]


def _q_field_variants(field, token):
    """Q(field__icontains=вариант) объединённые через ИЛИ."""
    q = Q()
    for v in _ci_variants(token):
        q |= Q(**{f'{field}__icontains': v})
    return q


def _q_token_anywhere(token, include_body=False):
    """Один токен общего поиска: любое поле из SEARCH_ANYWHERE_FIELDS (ИЛИ).

    include_body=True — дополнительно ищем в теле письма (body_text),
    т.е. режим «Тема + тело письма».
    """
    q = Q()
    for field in SEARCH_ANYWHERE_FIELDS:
        q |= _q_field_variants(field, token)
    if include_body:
        q |= _q_field_variants('body_text', token)
    return q


def filter_emails(queryset, cleaned_data):
    # Строгий поиск: каждое поле ищет ТОЛЬКО в своём поле письма.
    # Мульти-ввод: токены через запятую объединяются через ИЛИ внутри поля.
    # Разные поля комбинируются через И (цепочка .filter()).
    if cleaned_data.get('sender'):
        q = Q()
        for t in _split_tokens(cleaned_data['sender']):
            q |= _q_field_variants('sender', t) | _q_field_variants('sender_name', t)
        if q:
            queryset = queryset.filter(q)
    if cleaned_data.get('receiver'):
        q = Q()
        for t in _split_tokens(cleaned_data['receiver']):
            q |= _q_field_variants('receiver', t)
        if q:
            queryset = queryset.filter(q)
    if cleaned_data.get('cc'):
        q = Q()
        for t in _split_tokens(cleaned_data['cc']):
            q |= _q_field_variants('cc', t)
        if q:
            queryset = queryset.filter(q)
    if cleaned_data.get('project_site'):
        queryset = queryset.filter(project_site__in=cleaned_data['project_site'])
    if cleaned_data.get('contractor'):
        queryset = queryset.filter(contractor__in=cleaned_data['contractor'])
    if cleaned_data.get('category'):
        queryset = queryset.filter(category__in=cleaned_data['category'])
    if cleaned_data.get('building_type'):
        queryset = queryset.filter(building_type__in=cleaned_data['building_type'])
    if cleaned_data.get('info'):
        queryset = queryset.filter(info__in=cleaned_data['info'])
    if cleaned_data.get('tags'):
        queryset = queryset.filter(email_tags__tag__in=cleaned_data['tags']).distinct()
    if cleaned_data.get('has_attachments'):
        queryset = queryset.filter(attachments__isnull=False).distinct()
    if cleaned_data.get('is_important'):
        queryset = queryset.filter(is_important=True)
    if cleaned_data.get('is_unread'):
        queryset = queryset.filter(is_read=False)
    if cleaned_data.get('date_from') or cleaned_data.get('date_to'):
        # Дата письма: email_stamp, а для отправленных из приложения
        # (там штамп пуст) — sent_at/creation_stamp, иначе их не найти.
        queryset = queryset.annotate(
            _eff_date=Coalesce(TruncDate('email_stamp'), TruncDate('sent_at'),
                               TruncDate('creation_stamp')),
        )
        if cleaned_data.get('date_from'):
            queryset = queryset.filter(_eff_date__gte=cleaned_data['date_from'])
        if cleaned_data.get('date_to'):
            queryset = queryset.filter(_eff_date__lte=cleaned_data['date_to'])
    if cleaned_data.get('folder'):
        queryset = queryset.filter(folder=cleaned_data['folder'])
    if cleaned_data.get('sent_status'):
        queryset = queryset.filter(sent_status=cleaned_data['sent_status'])
    if cleaned_data.get('search'):
        query = (cleaned_data['search'] or '').strip()
        # Общий поиск — везде (ИЛИ по полям). Слова через пробел/запятую —
        # каждое должно найтись где-то (И): «совещание К-1» найдёт
        # «Совещание 10.09.25 на К-1» независимо от регистра.
        # search_scope: '' (везде без тела) / subject (только тема) /
        # subject_body (везде + тело письма).
        scope = cleaned_data.get('search_scope') or ''
        tokens = [t for t in query.replace(',', ' ').replace(';', ' ').split() if t]
        if scope == 'subject':
            for tok in tokens:
                queryset = queryset.filter(_q_field_variants('subject', tok))
        else:
            include_body = scope == 'subject_body'
            for tok in tokens:
                queryset = queryset.filter(_q_token_anywhere(tok, include_body=include_body))
    return queryset


def _canonical_top_addresses(field, limit=200):
    """SRP: топ канонических bare-адресов поля (единый путь для всех подсказок пикера).

    Сырые алиасы без @ (обрезки 'Name <localpart', имена) сюда не попадают.
    """
    from collections import Counter
    from .utils import canonical_address_list
    counter = Counter()
    rows = (
        Email.objects.exclude(**{f'{field}__isnull': True}).exclude(**{field: ''})
        .values_list(field, flat=True)[:10000]
    )
    for raw in rows:
        if not raw or '@' not in raw:
            continue
        canon = canonical_address_list(raw)
        if not canon:
            continue
        for addr in canon.split(','):
            addr = addr.strip()
            if addr:
                counter[addr] += 1
    return sorted(addr for addr, _ in counter.most_common(limit))


def _get_email_field_suggestions(limit=200):
    """Подсказки для полей почты: ТОЛЬКО твёрдые bare-адреса, один путь для всех полей."""
    return {
        'all_senders': _canonical_top_addresses('sender', 300),
        'all_receivers': _canonical_top_addresses('receiver', limit),
        'all_cc_addresses': _canonical_top_addresses('cc', limit),
    }


def _get_email_view_settings(request):
    """Настройки отображения списка писем текущего пользователя.

    Возвращает dict для шаблонов: show_body_preview, preview_length.
    Незалогиненным (на всякий случай) — дефолты без записи в БД.
    """
    defaults = {
        'show_body_preview': True,
        'preview_length': EmailViewSettings.DEFAULT_PREVIEW_LENGTH,
    }
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False):
        return defaults
    obj, _ = EmailViewSettings.objects.get_or_create(user=user)
    return {
        'show_body_preview': obj.show_body_preview,
        'preview_length': obj.preview_length or EmailViewSettings.DEFAULT_PREVIEW_LENGTH,
    }


@login_required
def email_settings_modal(request):
    """Модалка «Настройки почты»: раздел «Тема письма»."""
    obj, _ = EmailViewSettings.objects.get_or_create(user=request.user)
    return render(request, 'email_ui/partials/email_settings_modal.html', {
        'view_settings': obj,
        'min_len': EmailViewSettings.MIN_PREVIEW_LENGTH,
        'max_len': EmailViewSettings.MAX_PREVIEW_LENGTH,
    })


@login_required
@require_http_methods(['POST'])
def save_email_settings(request):
    """Сохранение настроек отображения списка писем.

    Значения всегда клэмпятся к допустимым, поэтому ответ — всегда успех:
    htmx по HX-Refresh перезагружает страницу и список перерисовывается.
    """
    obj, _ = EmailViewSettings.objects.get_or_create(user=request.user)
    obj.show_body_preview = request.POST.get('show_body_preview') in ('true', 'True', '1', 'on')
    try:
        obj.preview_length = int(request.POST.get('preview_length', obj.preview_length))
    except (TypeError, ValueError):
        obj.preview_length = EmailViewSettings.DEFAULT_PREVIEW_LENGTH
    obj.clamp_preview_length()
    obj.save()
    messages.success(request, 'Настройки почты сохранены')
    response = HttpResponse(status=204)
    response['HX-Refresh'] = 'true'
    return response


@login_required
def inbox_view(request, folder='inbox'):
    emails = Email.objects.filter(folder=folder).select_related(
        'project_site', 'contractor', 'category', 'building_type'
    ).prefetch_related('attachments', 'tasks')

    filter_form = EmailFilterForm(request.GET)
    if filter_form.is_valid():
        emails = filter_emails(emails, filter_form.cleaned_data)

    emails, current_sort, current_order = apply_sorting(emails, request)

    paginator = Paginator(emails, PER_PAGE)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    selected_project_sites = request.GET.getlist('project_site')
    selected_contractors = request.GET.getlist('contractor')
    selected_building_types = request.GET.getlist('building_type')
    selected_categories = request.GET.getlist('category')
    selected_info = request.GET.getlist('info')
    selected_tags = request.GET.getlist('tags')

    # Данные для преобразования ID в названия в шаблоне и JS
    filter_data = {
        'project_site': {str(obj.id): obj.name for obj in ProjectSite.objects.all()},
        'contractor': {str(obj.id): obj.name for obj in Contractor.objects.all()},
        'building_type': {str(obj.id): obj.name for obj in BuildingType.objects.all()},
        'category': {str(obj.id): obj.name for obj in Category.objects.all()},
        'info': dict(InfoChoices.choices),
        'tags': {str(obj.id): obj.name for obj in EmailTag.objects.all()},
    }

    active_filters = {
        'project_site': bool(selected_project_sites),
        'contractor': bool(selected_contractors),
        'building_type': bool(selected_building_types),
        'category': bool(selected_categories),
    }
    context = {
        'folder': folder,
        'page_obj': page_obj,
        'filter_form': filter_form,
        'total_count': paginator.count,
        'current_sort': current_sort,
        'current_order': current_order,
        'selected_project_sites': selected_project_sites,
        'selected_contractors': selected_contractors,
        'selected_building_types': selected_building_types,
        'selected_categories': selected_categories,
        'selected_info': selected_info,
        'selected_tags': selected_tags,
        'filter_data': filter_data,
        'all_tags': EmailTag.objects.all(),
        'clean_params': _clean_query_string(request),
        **_get_email_field_suggestions(),
        'email_list_back_url': _build_back_url(request, folder),
        'active_filters': active_filters,
        'email_view_settings': _get_email_view_settings(request),
    }
    return render(request, 'email_ui/inbox.html', context)


@login_required
@require_http_methods(['GET'])
def email_list_partial(request):
    """Частичное обновление списка писем."""
    folder = request.GET.get('folder', 'inbox')
    emails = Email.objects.filter(folder=folder).select_related(
        'project_site', 'contractor', 'building_type', 'category'
    ).prefetch_related('attachments')

    filter_form = EmailFilterForm(request.GET)
    if filter_form.is_valid():
        emails = filter_emails(emails, filter_form.cleaned_data)

    emails, current_sort, current_order = apply_sorting(emails, request)

    paginator = Paginator(emails, PER_PAGE)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    active_filters = {
        'project_site': bool(request.GET.getlist('project_site')),
        'contractor': bool(request.GET.getlist('contractor')),
        'building_type': bool(request.GET.getlist('building_type')),
        'category': bool(request.GET.getlist('category')),
    }

    # Если запрос от индикатора бесконечной прокрутки – возвращаем только строки и новый индикатор
    if request.GET.get('_infinite'):
        context = {
            'page_obj': page_obj,
            'clean_params': _clean_query_string(request),
            'email_list_back_url': _build_back_url(request, folder),
            'active_filters': active_filters,
            'email_view_settings': _get_email_view_settings(request),
        }
        return render(request, 'email_ui/partials/email_rows.html', context)

    # Обычный запрос (первая загрузка, сортировка, фильтрация) – возвращаем полную таблицу
    context = {
        'folder': folder,
        'page_obj': page_obj,
        'current_sort': current_sort,
        'current_order': current_order,
        'clean_params': _clean_query_string(request),
        'email_list_back_url': _build_back_url(request, folder),
        'active_filters': active_filters,
        'email_view_settings': _get_email_view_settings(request),
        'oob_sync': True,
    }
    return render(request, 'email_ui/partials/email_list.html', context)


@login_required
def filter_form_partial(request):
    """Частичное обновление формы фильтрации (для каскадных фильтров)."""
    folder = request.GET.get('folder', 'inbox')
    filter_form = EmailFilterForm(request.GET)
    context = {
        'filter_form': filter_form,
        'folder': folder,
        'selected_project_sites': request.GET.getlist('project_site'),
        'selected_contractors': request.GET.getlist('contractor'),
        'selected_building_types': request.GET.getlist('building_type'),
        'selected_categories': request.GET.getlist('category'),
        'selected_info': request.GET.getlist('info'),
        'selected_tags': request.GET.getlist('tags'),
        **_get_email_field_suggestions(),
    }
    return render(request, 'email_ui/partials/filter_form.html', context)


@login_required
def email_detail(request, pk):
    """Полноценная страница просмотра письма.

    Для черновиков (folder='drafts') — редирект на draft_edit (compose-редактор).
    """
    email = get_object_or_404(
        Email.objects.select_related(
            'project_site', 'contractor', 'category', 'building_type'
        ).prefetch_related('attachments', 'tasks'),
        pk=pk
    )

    # Черновики открываются в compose-редакторе
    if email.folder == 'drafts':
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(
            reverse('email_ui:draft_edit', args=[pk]) +
            '?next=' + (request.GET.get('next') or reverse('email_ui:inbox', args=['drafts']))
        )

    if not email.is_read:
        email.is_read = True
        email.save(update_fields=['is_read'])

    raw_next = request.GET.get('next') or reverse('email_ui:inbox', args=[email.folder])
    next_url = _sanitize_next_url(raw_next)

    context = {
        'email': email,
        'metadata_form': EmailMetadataForm(instance=email),
        'all_tags': EmailTag.objects.all(),
        'next_url': next_url,
    }
    return render(request, 'email_ui/email_detail.html', context)


@login_required
def email_detail_modal(request, pk):
    """Возвращает фрагмент с деталями письма для модального окна.

    Для черновиков — редирект на draft_edit.
    """
    email = get_object_or_404(
        Email.objects.select_related(
            'project_site', 'contractor', 'category', 'building_type'
        ).prefetch_related('attachments', 'tasks'),
        pk=pk
    )

    if email.folder == 'drafts':
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(reverse('email_ui:draft_edit', args=[pk]))

    if not email.is_read:
        email.is_read = True
        email.save(update_fields=['is_read'])

    context = {
        'email': email,
        'metadata_form': EmailMetadataForm(instance=email),
        'all_tags': EmailTag.objects.all(),
    }
    return render(request, 'email_ui/partials/email_detail_modal_content.html', context)


@login_required
@require_http_methods(['POST'])
def mark_email_as_read(request, pk):
    """Помечает письмо как прочитанное."""
    email = get_object_or_404(Email, pk=pk)
    if not email.is_read:
        email.is_read = True
        email.save(update_fields=['is_read'])
    return HttpResponse(status=204)  # No content, успешно


@login_required
def email_body(request, pk):
    """Возвращает очищенный HTML письма в «бумажной» карточке с переключателем режимов."""
    email = get_object_or_404(Email, pk=pk)
    html_path = email.get_html_file_path()

    def _frame(inner: str) -> str:
        return (
            f'<div class="letter-frame letter-paper" id="letter-frame-{pk}">'
            f'<div class="letter-toolbar">'
            f'<span class="letter-toolbar-label"><i class="bi bi-card-text me-1"></i>Отображение письма</span>'
            f'<div class="letter-toolbar-controls">'
            f'<label class="letter-fontscale" title="Размер шрифта письма">'
            f'<i class="bi bi-type"></i>'
            f'<input type="range" min="12" max="24" step="1" value="16" '
            f'oninput="setLetterFontSize({pk},this.value,this)" title="Размер шрифта письма">'
            f'<span id="letter-fontval-{pk}">16</span>'
            f'</label>'
            f'<div class="letter-mode-switch" role="group">'
            f'<button type="button" class="active" data-mode="letter-paper" onclick="setLetterMode({pk},\'letter-paper\',this)">Светлое</button>'
            f'<button type="button" data-mode="letter-dark" onclick="setLetterMode({pk},\'letter-dark\',this)">Тёмное</button>'
            f'<button type="button" data-mode="letter-auto" onclick="setLetterMode({pk},\'letter-auto\',this)">Оригинал</button>'
            f'</div></div></div>'
            f'<div class="letter-content">{inner}</div></div>'
        )

    if not html_path or not os.path.exists(html_path):
        return HttpResponse(_frame('<p class="text-muted">Файл письма не найден</p>'))
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            raw_html = f.read()
        resolved = resolve_inline_image_urls(email, raw_html)
        cleaned = clean_email_html(resolved)
        segmented = segment_letter_html(cleaned)
        return HttpResponse(_frame(segmented))
    except Exception as e:
        return HttpResponse(_frame(f'<p>Ошибка загрузки: {e}</p>'))


@login_required
def serve_inline_attachment(request, att_id):
    """Отдаёт вложение inline — для картинок, встроенных в тело письма."""
    att = get_object_or_404(Attachment, pk=att_id)
    if not os.path.exists(att.file_path):
        raise Http404("Файл не найден")
    content_type, encoding = mimetypes.guess_type(att.filename)
    if not content_type:
        content_type = att.content_type or 'application/octet-stream'
    response = FileResponse(open(att.file_path, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'inline; filename="{att.filename}"'
    return response


@login_required
def download_attachment(request, att_id):
    """Скачивание вложения."""
    att = get_object_or_404(Attachment, pk=att_id)
    if not os.path.exists(att.file_path):
        raise Http404("Файл не найден")
    content_type, encoding = mimetypes.guess_type(att.filename)
    if not content_type:
        content_type = 'application/octet-stream'
    response = FileResponse(open(att.file_path, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{att.filename}"'
    return response


@login_required
@require_http_methods(['POST'])
def edit_metadata(request, pk):
    """Редактирование метаданных письма."""
    email = get_object_or_404(Email, pk=pk)
    form = EmailMetadataForm(request.POST, instance=email)
    if form.is_valid():
        cd = form.cleaned_data
        # If any metadata field is filled, auto-mark as important
        has_metadata = any(v for k, v in cd.items() if k in ('project_site', 'contractor', 'building_type', 'category') and v)
        if has_metadata and not email.is_important:
            email.is_important = True
        form.save()
        return render(request, 'email_ui/partials/metadata_display.html', {'email': email})
    else:
        return render(request, 'email_ui/partials/metadata_form.html', {
            'email': email,
            'metadata_form': form,
        }, status=400)


@login_required
@require_http_methods(['POST'])
def add_attachment(request, pk):
    """Добавить вложение к письму."""
    email = get_object_or_404(Email, pk=pk)
    uploaded_file = request.FILES.get('attachment_file')
    if not uploaded_file:
        return HttpResponseBadRequest('Файл не выбран')
    try:
        att = Attachment.objects.create(
            email=email,
            file_path='',
            filename=uploaded_file.name,
            size=uploaded_file.size or 0,
            content_type=uploaded_file.content_type or '',
        )
        os.makedirs(os.path.dirname(email.link or ''), exist_ok=True)
        if email.link:
            file_path = os.path.join(email.link, uploaded_file.name)
            with open(file_path, 'wb+') as dest:
                for chunk in uploaded_file.chunks():
                    dest.write(chunk)
            att.file_path = file_path
            att.save(update_fields=['file_path'])
        messages.success(request, f'Файл "{uploaded_file.name}" добавлен')
        detail_url = reverse('email_ui:email_detail', args=[pk])
        raw_next = request.POST.get('next') or request.GET.get('next')
        if raw_next:
            from urllib.parse import quote
            detail_url += '?next=' + quote(raw_next, safe='')
        return redirect(detail_url)
    except Exception as e:
        messages.error(request, f'Ошибка добавления файла: {e}')
        detail_url = reverse('email_ui:email_detail', args=[pk])
        raw_next = request.POST.get('next') or request.GET.get('next')
        if raw_next:
            from urllib.parse import quote
            detail_url += '?next=' + quote(raw_next, safe='')
        return redirect(detail_url)


@login_required
def edit_metadata_form(request, pk):
    """Возвращает форму редактирования метаданных."""
    email = get_object_or_404(Email, pk=pk)
    form = EmailMetadataForm(instance=email)
    return render(request, 'email_ui/partials/metadata_form.html', {'email': email, 'metadata_form': form})


@login_required
def metadata_display(request, pk):
    """Возвращает отображение метаданных."""
    email = get_object_or_404(Email, pk=pk)
    return render(request, 'email_ui/partials/metadata_display.html', {'email': email})


@login_required
@require_http_methods(['POST'])
def toggle_important(request, pk):
    """Переключить флаг важности письма."""
    email = get_object_or_404(Email, pk=pk)
    email.is_important = not email.is_important
    email.save(update_fields=['is_important'])
    if request.headers.get('HX-Request'):
        btn_class = 'btn-warning' if email.is_important else 'btn-outline-secondary'
        icon_class = 'bi-star-fill' if email.is_important else 'bi-star'
        return HttpResponse(
            f'<button class="btn btn-sm {btn_class}" hx-post="{reverse("email_ui:toggle_important", args=[pk])}" '
            f'hx-target="this" hx-swap="outerHTML" title="Важно">'
            f'<i class="bi {icon_class}"></i>'
            f'</button>'
        )
    return JsonResponse({'is_important': email.is_important})


@login_required
@require_http_methods(['POST'])
def move_to_folder(request, pk):
    """Перемещение письма в другую папку."""
    email = get_object_or_404(Email, pk=pk)
    folder = request.POST.get('folder')
    if folder in dict(Email.FOLDER_CHOICES):
        email.folder = folder
        email.save(update_fields=['folder'])
        messages.success(request, f'Письмо перемещено в папку "{folder}"')
        return HttpResponse(status=204)
    return HttpResponseBadRequest('Некорректная папка')


@login_required
def attach_to_tasks_modal(request, pk):
    """Большое модальное окно выбора задач: поиск + фильтры как в админке."""
    email = get_object_or_404(Email, pk=pk)
    q = (request.GET.get('q') or '').strip()
    project = request.GET.get('project') or ''
    status = request.GET.get('status') or ''
    date_from = request.GET.get('date_from') or ''
    date_to = request.GET.get('date_to') or ''

    tasks = TaskNode.objects.select_related(
        'project_site', 'status', 'contractor'
    ).order_by('-due_date')
    if q:
        tasks = tasks.filter(
            Q(name__icontains=q) | Q(project_site__name__icontains=q) |
            Q(contractor__name__icontains=q)
        )
    if project:
        tasks = tasks.filter(project_site_id=project)
    if status:
        tasks = tasks.filter(status_id=status)
    if date_from:
        tasks = tasks.filter(due_date__gte=date_from)
    if date_to:
        tasks = tasks.filter(due_date__lte=date_to)

    context = {
        'email': email,
        'tasks': tasks[:100],
        'projects': ProjectSite.objects.all().order_by('name'),
        'statuses': Status.objects.all().order_by('name'),
        'attached_ids': set(email.tasks.values_list('id', flat=True)),
        'sel': {'q': q, 'project': project, 'status': status,
                'date_from': date_from, 'date_to': date_to},
    }
    return render(request, 'email_ui/partials/task_selector.html', context)


@login_required
def attach_tasks_page(request, pk):
    """Полноценная страница привязки задач к письму (вместо модального окна)."""
    email = get_object_or_404(Email, pk=pk)
    q = (request.GET.get('q') or '').strip()
    project = request.GET.get('project') or ''
    contractor = request.GET.get('contractor') or ''
    status = request.GET.get('status') or ''
    date_from = request.GET.get('date_from') or ''
    date_to = request.GET.get('date_to') or ''

    tasks = TaskNode.objects.select_related(
        'project_site', 'status', 'contractor'
    ).order_by('-due_date')
    if q:
        tasks = tasks.filter(
            Q(name__icontains=q) | Q(project_site__name__icontains=q) |
            Q(contractor__name__icontains=q)
        )
    if project:
        tasks = tasks.filter(project_site_id=project)
    if contractor:
        tasks = tasks.filter(contractor_id=contractor)
    if status:
        tasks = tasks.filter(status_id=status)
    if date_from:
        tasks = tasks.filter(due_date__gte=date_from)
    if date_to:
        tasks = tasks.filter(due_date__lte=date_to)

    context = {
        'email': email,
        'tasks': tasks[:100],
        'projects': ProjectSite.objects.all().order_by('name'),
        'contractors': Contractor.objects.all().order_by('name'),
        'statuses': Status.objects.all().order_by('name'),
        'attached_ids': set(email.tasks.values_list('id', flat=True)),
        'today': timezone.localdate(),
        'sel': {'q': q, 'project': project, 'contractor': contractor,
                'status': status, 'date_from': date_from, 'date_to': date_to},
    }
    return render(request, 'email_ui/attach_tasks_page.html', context)


@login_required
def email_tasks_partial(request, pk):
    """Обновляемый блок привязанных задач письма."""
    email = get_object_or_404(Email.objects.prefetch_related('tasks'), pk=pk)
    return render(request, 'email_ui/partials/email_tasks_body.html', {'email': email})


@login_required
@require_http_methods(['POST'])
def attach_tasks(request, pk):
    """Привязка задач к письму с редиректом на страницу письма."""
    email = get_object_or_404(Email, pk=pk)
    task_ids = sanitize_id_list(request.POST.getlist('tasks'))
    tasks = TaskNode.objects.filter(id__in=task_ids) if task_ids else TaskNode.objects.none()
    if tasks:
        email.tasks.add(*tasks)
        names = ', '.join(t.name[:40] for t in tasks[:3])
        msg = f'Письмо привязано к задачам ({len(tasks)}): {names}'
        messages.success(request, msg)
    else:
        msg = 'Не выбрано ни одной задачи'
        messages.warning(request, msg)
    next_url = request.POST.get('next') or reverse('email_ui:email_detail', args=[pk])
    return redirect(next_url)


@login_required
@require_http_methods(['POST'])
def detach_task(request, pk, task_id):
    """Отвязка задачи: бейдж удаляется, показывается тост."""
    email = get_object_or_404(Email, pk=pk)
    task = get_object_or_404(TaskNode, pk=task_id)
    email.tasks.remove(task)
    return HttpResponse(
        f'<script>showToast("Задача «{task.name[:40]}» отвязана от письма","info")</script>'
    )


@login_required
@require_http_methods(['POST'])
def bulk_action(request):
    """Массовые операции над выбранными письмами."""
    action = request.POST.get('action')
    select_all = request.POST.get('select_all')
    folder = request.POST.get('folder', 'inbox')

    if select_all == '1':
        # Apply action to ALL emails matching current filters
        emails = Email.objects.filter(folder=folder).select_related(
            'project_site', 'contractor'
        ).prefetch_related('attachments')
        filter_params = request.POST.get('filter_params', '')
        from django.http import QueryDict
        filter_qd = QueryDict(filter_params)
        filter_form = EmailFilterForm(filter_qd)
        if filter_form.is_valid():
            emails = filter_emails(emails, filter_form.cleaned_data)
    else:
        raw_ids = request.POST.getlist('selected_emails')
        email_ids = sanitize_id_list(raw_ids)
        if not email_ids:
            return HttpResponseBadRequest('Нет писем')
        emails = Email.objects.filter(id__in=email_ids)

    if action == 'move':
        target_folder = request.POST.get('move_to') or request.POST.get('folder')
        if target_folder in dict(Email.FOLDER_CHOICES):
            emails.update(folder=target_folder)
            messages.success(request, f'{emails.count()} писем перемещено')
    elif action == 'mark_read':
        emails.update(is_read=True)
    elif action == 'mark_unread':
        emails.update(is_read=False)
    elif action == 'mark_important':
        emails.update(is_important=True)
    elif action == 'mark_unimportant':
        emails.update(is_important=False)
    elif action == 'delete':
        emails.update(folder='trash')
        messages.success(request, f'{emails.count()} писем перемещено в корзину')
    else:
        return HttpResponseBadRequest('Неизвестное действие')

    folder = request.POST.get('folder', 'inbox')

    # При HTMX-запросе возвращаем частичное обновление, а не редирект
    if request.headers.get('HX-Request'):
        emails = Email.objects.filter(folder=folder).select_related(
            'project_site', 'contractor'
        ).prefetch_related('attachments')
        filter_params = request.POST.get('filter_params', '')
        if filter_params:
            from django.http import QueryDict
            filter_qd = QueryDict(filter_params)
            filter_form = EmailFilterForm(filter_qd)
            if filter_form.is_valid():
                emails = filter_emails(emails, filter_form.cleaned_data)
        emails, current_sort, current_order = apply_sorting(emails, request)
        paginator = Paginator(emails, PER_PAGE)
        page_obj = paginator.get_page(1)
        context = {
            'folder': folder,
            'page_obj': page_obj,
            'current_sort': current_sort,
            'current_order': current_order,
            'clean_params': _clean_query_string(request),
            'email_list_back_url': _build_back_url(request, folder),
            'oob_sync': True,
        }
        return render(request, 'email_ui/partials/email_list.html', context)
    filter_params = request.POST.get('filter_params', '')
    url = reverse('email_ui:inbox', args=[folder])
    if filter_params:
        url += '?' + filter_params
    return redirect(url)


@login_required
def filter_field_modal(request, field_name):
    folder = request.GET.get('folder', 'inbox')
    selected_values = _get_list_from_request(request, 'selected')
    selected_projects = _get_list_from_request(request, 'project_site')

    # Логируем входные параметры
    logger.debug(f"filter_field_modal: field={field_name}, folder={folder}, "
                 f"selected={selected_values}, project_site={selected_projects}")

    context = {
        'field_name': field_name,
        'folder': folder,
        'selected_values': selected_values,
    }

    if field_name == 'project_site':
        queryset = ProjectSite.objects.all()
        context['items'] = queryset
        context['title'] = 'Выберите проекты'
        logger.debug(f"ProjectSite queryset count: {queryset.count()}")

    elif field_name == 'contractor':
        queryset = Contractor.objects.all()
        if selected_projects:
            # Фильтруем подрядчиков, которые имеют письма с выбранными проектами
            queryset = queryset.filter(email__project_site__in=selected_projects).distinct()
            logger.debug(f"Contractor filtered by projects {selected_projects}, count: {queryset.count()}")
        else:
            logger.debug("Contractor queryset (no project filter)")
        context['items'] = queryset
        context['title'] = 'Выберите подрядчиков'

    elif field_name == 'building_type':
        queryset = BuildingType.objects.all()
        if selected_projects:
            queryset = queryset.filter(email__project_site__in=selected_projects).distinct()
            logger.debug(f"BuildingType filtered by projects {selected_projects}, count: {queryset.count()}")
        else:
            logger.debug("BuildingType queryset (no project filter)")
        context['items'] = queryset
        context['title'] = 'Выберите здания'

    elif field_name == 'category':
        context['items'] = Category.objects.all()
        context['title'] = 'Выберите категории'
        logger.debug(f"Category queryset count: {Category.objects.count()}")

    elif field_name == 'info':
        context['items'] = [{'id': v, 'name': l} for v, l in InfoChoices.choices]
        context['title'] = 'Выберите тип информации'
        logger.debug(f"InfoChoices count: {len(InfoChoices.choices)}")

    elif field_name == 'tags':
        context['items'] = EmailTag.objects.all()
        context['title'] = 'Выберите теги'
        logger.debug(f"EmailTag count: {EmailTag.objects.count()}")

    elif field_name == 'sent_status':
        choices = [
            ('draft', 'Черновик'), ('queued', 'В очереди'),
            ('sent', 'Отправлено'), ('failed', 'Ошибка'),
        ]
        context['items'] = [{'id': v, 'name': l} for v, l in choices]
        context['title'] = 'Выберите статус отправки'

    else:
        logger.warning(f"Invalid field_name: {field_name}")
        return HttpResponseBadRequest('Неверное поле')

    # Запрещаем кэширование ответа браузером
    response = render(request, 'email_ui/partials/filter_field_modal.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@login_required
def unread_count(request):
    """Возвращает JSON со счётчиками для боковой панели."""
    base = Email.objects.filter(folder='inbox')
    data = {
        'inbox': base.filter(is_read=False).count(),
        'important': base.filter(is_important=True).count(),
        'attachments': base.filter(attachments__isnull=False).distinct().count(),
        'unread': base.filter(is_read=False).count(),
        'drafts': Email.objects.filter(folder='drafts').count(),
        'sent': Email.objects.filter(folder='sent').count(),
    }
    if request.headers.get('HX-Request') == 'true':
        return HttpResponse(str(data['inbox']))
    return JsonResponse(data)


def _get_list_from_request(request, param_name):
    """
    Возвращает список значений параметра, поддерживая как множественные параметры,
    так и строку с запятыми.
    """
    values = request.GET.getlist(param_name)
    if not values and request.GET.get(param_name):
        values = request.GET.get(param_name).split(',')
    # Удаляем пустые строки
    return [v for v in values if v]


@login_required
@require_http_methods(['POST'])
def fetch_emails(request):
    """
    Запускает процесс получения почты через IMAP.
    После завершения редиректит обратно на страницу, с которой пришёл запрос.
    """
    # Количество писем для загрузки (по умолчанию 10)
    email_limit = int(request.POST.get('mail_count', 10))

    # Соответствие папок IMAP и внутренних типов
    initial_folder_list = {
        'INBOX': EmailType.IN.name,
        'Отправленные': EmailType.OUT.name
    }

    actions_list = []  # Успешно обработанные
    scip_list = []  # Пропущенные (уже есть)

    # Базовая директория для сохранения вложений
    directory = os.path.join(E_MAIL_DIRECTORY, 'imap_attachments')

    for folder, folder_db_name in initial_folder_list.items():
        root_path = os.path.join(directory, folder)
        parser = ParsingImapEmailToDB(root_path)
        parser.main(folder_db_name, folder, limit=email_limit)
        actions_list.append(parser.create_action_list)
        scip_list.append(parser.skip_action_list)

    # Преобразуем списки списков в плоский список
    actions_list = flatten(actions_list)
    scip_list = flatten(scip_list)

    if actions_list:
        res_list = [str(val) for val in actions_list]
        messages.success(request, f"Почта сохранена для следующих позиций: {', '.join(res_list)}")
    else:
        messages.info(request, "Новых писем не найдено")

    # Редирект обратно на исходную страницу (список писем)
    next_url = request.POST.get('next', reverse('email_ui:inbox_default'))
    return redirect(next_url)


@login_required
def attachments_modal(request, pk):
    """Возвращает содержимое модального окна со всеми вложениями письма."""
    email = get_object_or_404(Email, pk=pk)
    return render(request, 'email_ui/partials/attachments_modal.html', {'email': email})


@login_required
def open_attachment_folder(request, pk):
    """Открывает папку с вложениями письма в проводнике."""
    email = get_object_or_404(Email, pk=pk)
    folder_path = email.link
    if not folder_path or not os.path.exists(folder_path):
        return JsonResponse({'success': False, 'error': 'Папка не найдена'})
    try:
        if platform.system() == 'Windows':
            os.startfile(folder_path)
        elif platform.system() == 'Darwin':  # macOS
            subprocess.Popen(['open', folder_path])
        else:  # Linux
            subprocess.Popen(['xdg-open', folder_path])
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def _reply_all_recipients(email, user_email=''):
    """To/Cc для «Ответить всем» по исходному письму.

    Единая логика для префилла модалки и fallback отправки:
    To — явный адрес отправителя; Cc — явные адреса из To/Cc
    минус отправитель, свои адреса (пользователь, YA_USER,
    аккаунт письма, все активные SMTP). Возвращает (to, cc, missing),
    где missing — entries без явного email (не подменяются контактами).
    """
    sender_email = resolve_sender_to_email(email.sender or '')
    excluded = set()
    if sender_email:
        excluded.add(sender_email.lower())
    if user_email:
        excluded.add(user_email.lower())
    from django.conf import settings
    ya_user = getattr(settings, 'YA_USER', '') or ''
    if ya_user:
        excluded.add(ya_user.lower())
    if email.smtp_account and email.smtp_account.from_email:
        excluded.add(email.smtp_account.from_email.lower())
    from email_ui.models import SMTPAccount
    for acc in SMTPAccount.objects.filter(is_active=True):
        if acc.from_email:
            excluded.add(acc.from_email.lower())
    cc_set, missing = set(), []
    for raw_field in (email.receiver, email.cc):
        if not raw_field:
            continue
        for entry in raw_field.split(','):
            entry = entry.strip()
            if not entry:
                continue
            addr = extract_email_address(entry)
            if not addr:
                # Явный email отсутствует - не подменяем контактом, фиксируем пропуск.
                missing.append(entry)
                continue
            if addr.lower() in excluded:
                continue
            cc_set.add(addr)
    return sender_email, ', '.join(sorted(cc_set)), missing


# ==================== Phase 2: Compose & Send ====================

@login_required
def compose_modal(request):
    """Редактор для создания нового письма."""
    form = ComposeEmailForm()
    contacts = Contact.objects.filter(is_active=True).prefetch_related('emails')
    return render(request, 'email_ui/partials/compose_modal.html', {
        'form': form,
        'mode': 'compose',
        'contacts': contacts,
        'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
        'next': request.GET.get('next', ''),
    })


@login_required
def reply_modal(request, pk, reply_type='reply'):
    """Модальное окно для ответа/пересылки."""
    email = get_object_or_404(Email, pk=pk)
    form = ComposeReplyForm(initial={'include_attachments': reply_type == 'forward'})

    subject_map = {
        'reply': f'Re: {email.subject}',
        'reply_all': f'Re: {email.subject}',
        'forward': f'Fwd: {email.subject}',
    }

    # Подгружаем тело исходного письма для цитирования
    body_text = ''
    load_original = reply_type in ('reply', 'reply_all', 'forward')
    if load_original:
        html_path = email.get_html_file_path()
        if html_path and os.path.exists(html_path):
            try:
                with open(html_path, 'r', encoding='utf-8') as f:
                    orig = f.read()
                    body_text = f'<br><hr><blockquote>{orig}</blockquote>'
            except Exception:
                pass

    to_addr = ''
    cc_addr = ''
    resolve_errors = []
    user_email = (request.user.email or '').lower() if request.user and hasattr(request.user, 'email') else ''

    if reply_type == 'reply':
        # Адрес получателя извлекается ТОЛЬКО явно из поля From.
        # Нечёткий поиск контактов запрещён - если email отсутствует, это ошибка.
        to_addr = resolve_sender_to_email(email.sender or '')
        if not to_addr:
            resolve_errors.append(
                'Не удалось определить email получателя для ответа: '
                'в поле отправителя письма нет явного адреса. Укажите его вручную.'
            )
    elif reply_type == 'reply_all':
        to_addr, cc_addr, missing = _reply_all_recipients(email, user_email)
        if not to_addr:
            resolve_errors.append(
                'Не удалось определить email отправителя для ответа: '
                'в поле отправителя письма нет явного адреса. Укажите его вручную.'
            )
        if missing:
            resolve_errors.append(
                'Часть получателей (поля To/Cc) не содержит явного email-адреса и была '
                'пропущена: ' + '; '.join(missing[:10]) +
                ('. Проверьте список получателей вручную перед отправкой.' if len(missing) <= 10
                 else ' и ещё ' + str(len(missing) - 10) + '... Проверьте список получателей вручную перед отправкой.')
            )
    elif reply_type == 'forward':
        to_addr = ''

    contacts = Contact.objects.filter(is_active=True).prefetch_related('emails')
    # Для reply/reply_all/forward: передаём вложения оригинального письма
    forward_attachments = list(email.attachments.all()) if reply_type in ('reply', 'reply_all', 'forward') else []

    context = {
        'form': form,
        'email': email,
        'mode': reply_type,
        'subject': subject_map.get(reply_type, email.subject),
        'to': to_addr,
        'cc': cc_addr,
        'error': ' '.join(resolve_errors) if resolve_errors else '',
        'body': body_text,
        'contacts': contacts,
        'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
        'forward_attachments': forward_attachments,
        'next': request.GET.get('next', ''),
    }
    return render(request, 'email_ui/partials/compose_modal.html', context)


@login_required
@require_http_methods(['POST'])
def send_email(request):
    """Отправка письма (AJAX)."""
    contacts = Contact.objects.filter(is_active=True).prefetch_related('emails')
    form = ComposeEmailForm(request.POST, request.FILES)
    if not form.is_valid():
        logger.warning(f'send_email form errors: {form.errors}')
        return render(request, 'email_ui/partials/compose_modal.html', {
            'form': form, 'mode': 'compose', 'contacts': contacts,
            'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
        }, status=400)

    cd = form.cleaned_data
    if not cd.get('to'):
        form.add_error('to', 'Укажите получателя')
        return render(request, 'email_ui/partials/compose_modal.html', {
            'form': form, 'mode': 'compose', 'contacts': contacts,
            'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
        }, status=400)

    cd = form.cleaned_data
    use_outlook = cd.get('use_outlook', False)

    try:
        uploaded_files = request.FILES.getlist('attachment_files')

        # Send
        sender = EmailSenderService(
            smtp_account=cd.get('smtp_account'),
            use_outlook=use_outlook,
        )

        to_list = extract_all_email_addresses(cd['to'])
        if not to_list:
            to_list = [addr.strip() for addr in cd['to'].split(',') if addr.strip()]

        from .utils import _EMAIL_STANDALONE_RE
        invalid = [a for a in to_list if not _EMAIL_STANDALONE_RE.match(a)]
        if invalid:
            form.add_error('to', f'Некорректные адреса: {", ".join(invalid)}')
            return render(request, 'email_ui/partials/compose_modal.html', {
                'form': form, 'mode': 'compose', 'contacts': contacts,
                'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
            }, status=400)

        cc_list = extract_all_email_addresses(cd.get('cc', ''))
        if not cc_list:
            cc_list = [addr.strip() for addr in cd.get('cc', '').split(',') if addr.strip()]
        bcc_list = extract_all_email_addresses(cd.get('bcc', ''))
        if not bcc_list:
            bcc_list = [addr.strip() for addr in cd.get('bcc', '').split(',') if addr.strip()]

        result = sender.send_via_smtp(
            to_emails=to_list,
            subject=cd['subject'],
            body_html=cd['body'],
            from_name=sender.smtp_account.from_name if sender.smtp_account else None,
            cc=cc_list if cc_list else None,
            bcc=bcc_list if bcc_list else None,
            attachments=uploaded_files if uploaded_files else None,
        )

        if result:
            # Create sent email record
            email_obj = Email.objects.create(
                email_type='OUT',
                subject=cd['subject'],
                sender=sender.smtp_account.from_email if sender.smtp_account else '',
                receiver=', '.join(to_list),
                cc=', '.join(cc_list) if cc_list else None,
                bcc=', '.join(bcc_list) if bcc_list else None,
                folder='sent',
                sent_status='sent',
                sent_at=timezone.now(),
                email_stamp=timezone.now(),
                is_read=True,
            )
            # Save uploaded files to disk and create Attachment records
            for f in uploaded_files:
                try:
                    att = Attachment(
                        email=email_obj,
                        filename=f.name,
                        size=f.size or 0,
                        content_type=f.content_type or '',
                        file_path='',
                    )
                    if email_obj.link:
                        os.makedirs(email_obj.link, exist_ok=True)
                        file_path = os.path.join(email_obj.link, f.name)
                        with open(file_path, 'wb+') as dest:
                            for chunk in f.chunks():
                                dest.write(chunk)
                        att.file_path = file_path
                    att.save()
                except Exception as e:
                    logger.warning(f'Ошибка сохранения вложения {f.name}: {e}')

            next_url = _sanitize_next_url(request.POST.get('next', ''))
            return render(request, 'email_ui/partials/send_success.html', {
                'message': 'Письмо отправлено',
                'next': next_url,
            })

    except Exception as e:
        logger.exception(f'Ошибка отправки: {e}')
        return render(request, 'email_ui/partials/compose_modal.html', {
            'form': form, 'mode': 'compose', 'contacts': contacts, 'error': str(e),
            'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
        }, status=400)


@login_required
@require_http_methods(['POST'])
def reply_send(request, pk):
    """Отправка ответа/пересылки на письмо."""
    email = get_object_or_404(Email, pk=pk)
    mode = request.POST.get('mode', 'reply')
    contacts = Contact.objects.filter(is_active=True).prefetch_related('emails')
    form = ComposeReplyForm(request.POST)
    if not form.is_valid():
        return render(request, 'email_ui/partials/compose_modal.html', {
            'form': form, 'email': email, 'mode': mode,
            'contacts': contacts, 'error': 'Форма невалидна',
            'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
        }, status=400)

    cd = form.cleaned_data
    body = cd.get('body', '')

    # Формируем получателей
    to_raw = cd.get('to', '')
    if not to_raw and mode in ('reply', 'reply_all'):
        # Адрес извлекается ТОЛЬКО явно из поля From. Нечёткий поиск запрещён.
        to_raw = resolve_sender_to_email(email.sender or '')
    to_list = extract_all_email_addresses(to_raw)

    cc_raw = cd.get('cc', '')
    if not cc_raw and mode == 'reply_all':
        # Тот же расчёт, что префилл модалки: с исключениями себя/отправителя/ящиков.
        sender_user_email = (
            (request.user.email or '').lower()
            if request.user and hasattr(request.user, 'email') else ''
        )
        _, cc_raw, _ = _reply_all_recipients(email, sender_user_email)
    cc_list = extract_all_email_addresses(cc_raw)

    # БЕЗОПАСНОСТЬ: адрес получателя обязателен и должен быть действительным.
    # Отсекаем любые невалидные адреса (защита от случайной подстановки).
    from .utils import _EMAIL_STANDALONE_RE
    to_list = [a for a in to_list if _EMAIL_STANDALONE_RE.match(a)]
    cc_list = [a for a in cc_list if _EMAIL_STANDALONE_RE.match(a)]
    if not to_list:
        return render(request, 'email_ui/partials/compose_modal.html', {
            'form': form, 'email': email, 'mode': mode, 'contacts': contacts,
            'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
            'error': 'Не указан ни один действительный email получателя. '
                     'Укажите адрес вручную перед отправкой ответа.',
        }, status=400)

    subject = cd.get('subject', '')
    if not subject:
        if mode == 'forward':
            subject = f'Fwd: {email.subject}' if email.subject else 'Fwd:'
        else:
            subject = f'Re: {email.subject}' if email.subject else 'Re:'

    # Collect excluded attachment IDs from form
    excluded_ids = set()
    for val in request.POST.getlist('exclude_attachments'):
        try:
            excluded_ids.add(sanitize_id(val))
        except (ValueError, TypeError):
            continue

    # Determine which attachments to forward
    include_attachments = cd.get('include_attachments', False) or mode == 'forward'
    attachment_objs = []
    if include_attachments:
        for att in email.attachments.all():
            if att.pk in excluded_ids:
                continue
            attachment_objs.append(att)

    # Include newly uploaded files
    for f in request.FILES.getlist('attachment_files'):
        attachment_objs.append(f)

    try:
        sender = EmailSenderService()
        sender.send_via_smtp(
            to_emails=to_list,
            subject=subject,
            body_html=body,
            cc=cc_list if cc_list else None,
            in_reply_to=email.message_id if mode != 'forward' else None,
            references=email.references or email.message_id if mode != 'forward' else None,
            attachments=attachment_objs if attachment_objs else None,
        )

        # Create reply/forward record
        new_email = Email.objects.create(
            email_type='OUT',
            subject=subject,
            sender=sender.smtp_account.from_email if sender.smtp_account else '',
            receiver=', '.join(to_list),
            cc=', '.join(cc_list) if cc_list else None,
            folder='sent',
            sent_status='sent',
            sent_at=timezone.now(),
            email_stamp=timezone.now(),
            is_read=True,
            in_reply_to=email.message_id if mode != 'forward' else None,
            thread_id=email.thread_id if mode != 'forward' else None,
        )

        # Save forwarded attachments to DB
        if include_attachments:
            for att in email.attachments.all():
                if att.pk in excluded_ids:
                    continue
                Attachment.objects.create(
                    email=new_email,
                    filename=att.filename,
                    file_path=att.file_path,
                    size=att.size,
                    content_type=att.content_type,
                )

        next_url = _sanitize_next_url(request.POST.get('next', ''))
        return render(request, 'email_ui/partials/send_success.html', {
            'message': 'Письмо отправлено',
            'next': next_url,
        })
    except Exception as e:
        logger.exception(f'Ошибка отправки ответа: {e}')
        return render(request, 'email_ui/partials/compose_modal.html', {
            'form': form, 'email': email, 'mode': mode,
            'contacts': contacts, 'error': str(e),
            'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
        }, status=400)


@login_required
def draft_edit(request, pk):
    """Открыть черновик в compose-редакторе для редактирования и отправки."""
    email = get_object_or_404(Email, pk=pk, folder='drafts')

    body_text = ''
    html_path = email.get_html_file_path()
    if html_path and os.path.exists(html_path):
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                body_text = f.read()
        except Exception:
            pass

    contacts = Contact.objects.filter(is_active=True).prefetch_related('emails')

    context = {
        'form': ComposeEmailForm(initial={
            'to': email.receiver or '',
            'cc': email.cc or '',
            'bcc': email.bcc or '',
            'subject': email.subject or '',
            'body': body_text,
        }),
        'mode': 'edit_draft',
        'draft_email': email,
        'draft_attachments': list(email.attachments.all()),
        'to': email.receiver or '',
        'cc': email.cc or '',
        'subject': email.subject or '',
        'body': body_text,
        'contacts': contacts,
        'contacts_json': _contacts_picker_json(contacts),
        'groups_json': _groups_picker_json(),
        'next': request.GET.get('next', ''),
    }
    return render(request, 'email_ui/draft_edit.html', context)


@login_required
@require_http_methods(['POST'])
def draft_send(request, pk):
    """Отправить письмо из черновика и удалить черновик."""
    draft = get_object_or_404(Email, pk=pk, folder='drafts')
    contacts = Contact.objects.filter(is_active=True).prefetch_related('emails')
    form = ComposeEmailForm(request.POST, request.FILES)

    if not form.is_valid():
        return render(request, 'email_ui/draft_edit.html', {
            'form': form, 'mode': 'edit_draft', 'draft_email': draft,
            'draft_attachments': list(draft.attachments.all()),
            'to': draft.receiver or '', 'cc': draft.cc or '',
            'subject': draft.subject or '', 'body': '',
            'contacts': contacts,
            'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
        }, status=400)

    cd = form.cleaned_data
    if not cd.get('to'):
        form.add_error('to', 'Укажите получателя')
        return render(request, 'email_ui/draft_edit.html', {
            'form': form, 'mode': 'edit_draft', 'draft_email': draft,
            'draft_attachments': list(draft.attachments.all()),
            'to': draft.receiver or '', 'cc': draft.cc or '',
            'subject': draft.subject or '', 'body': '',
            'contacts': contacts,
            'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
        }, status=400)

    try:
        uploaded_files = request.FILES.getlist('attachment_files')

        sender = EmailSenderService(
            smtp_account=cd.get('smtp_account'),
            use_outlook=cd.get('use_outlook', False),
        )

        to_list = extract_all_email_addresses(cd['to'])
        if not to_list:
            to_list = [addr.strip() for addr in cd['to'].split(',') if addr.strip()]

        from .utils import _EMAIL_STANDALONE_RE
        invalid = [a for a in to_list if not _EMAIL_STANDALONE_RE.match(a)]
        if invalid:
            form.add_error('to', f'Некорректные адреса: {", ".join(invalid)}')
            return render(request, 'email_ui/partials/compose_modal.html', {
                'form': form, 'mode': 'edit_draft', 'draft_email': draft,
                'draft_attachments': list(draft.attachments.all()),
                'contacts': contacts,
                'contacts_json': _contacts_picker_json(contacts),
                'groups_json': _groups_picker_json(),
            }, status=400)

        cc_list = extract_all_email_addresses(cd.get('cc', ''))
        if not cc_list:
            cc_list = [addr.strip() for addr in cd.get('cc', '').split(',') if addr.strip()]
        bcc_list = extract_all_email_addresses(cd.get('bcc', ''))
        if not bcc_list:
            bcc_list = [addr.strip() for addr in cd.get('bcc', '').split(',') if addr.strip()]

        # Собираем вложения: черновика (не удалённые) + новые загруженные
        excluded_ids = set()
        for val in request.POST.getlist('exclude_attachments'):
            try:
                excluded_ids.add(sanitize_id(val))
            except (ValueError, TypeError):
                continue

        attachment_objs = []
        for att in draft.attachments.all():
            if att.pk not in excluded_ids:
                attachment_objs.append(att)
        for f in uploaded_files:
            attachment_objs.append(f)

        result = sender.send_via_smtp(
            to_emails=to_list,
            subject=cd['subject'],
            body_html=cd['body'],
            from_name=sender.smtp_account.from_name if sender.smtp_account else None,
            cc=cc_list if cc_list else None,
            bcc=bcc_list if bcc_list else None,
            attachments=attachment_objs if attachment_objs else None,
        )

        if result:
            email_obj = Email.objects.create(
                email_type='OUT',
                subject=cd['subject'],
                sender=sender.smtp_account.from_email if sender.smtp_account else '',
                receiver=', '.join(to_list),
                cc=', '.join(cc_list) if cc_list else None,
                bcc=', '.join(bcc_list) if bcc_list else None,
                folder='sent',
                sent_status='sent',
                sent_at=timezone.now(),
                email_stamp=timezone.now(),
                is_read=True,
            )

            # Сохраняем вложения отправленного письма в БД
            for att in attachment_objs:
                if hasattr(att, 'pk') and att.pk:
                    # Это существующий Attachment из черновика — копируем запись
                    Attachment.objects.create(
                        email=email_obj,
                        filename=att.filename,
                        file_path=att.file_path,
                        size=att.size,
                        content_type=att.content_type,
                    )
                else:
                    # Это новый загруженный файл
                    try:
                        new_att = Attachment(
                            email=email_obj,
                            filename=att.name,
                            size=att.size or 0,
                            content_type=att.content_type or '',
                            file_path='',
                        )
                        if email_obj.link:
                            os.makedirs(email_obj.link, exist_ok=True)
                            file_path = os.path.join(email_obj.link, att.name)
                            with open(file_path, 'wb+') as dest:
                                for chunk in att.chunks():
                                    dest.write(chunk)
                            new_att.file_path = file_path
                        new_att.save()
                    except Exception as e:
                        logger.warning(f'Ошибка сохранения вложения {att.name}: {e}')

            # Удаляем черновик
            draft.delete()

            next_url = _sanitize_next_url(request.POST.get('next', ''))
            return render(request, 'email_ui/partials/send_success.html', {
                'message': 'Письмо отправлено',
                'next': next_url,
            })

    except Exception as e:
        logger.exception(f'Ошибка отправки черновика: {e}')
        return render(request, 'email_ui/draft_edit.html', {
            'form': form, 'mode': 'edit_draft', 'draft_email': draft,
            'draft_attachments': list(draft.attachments.all()),
            'to': draft.receiver or '', 'cc': draft.cc or '',
            'subject': draft.subject or '', 'body': '',
            'contacts': contacts, 'error': str(e),
            'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
        }, status=400)


@login_required
@require_http_methods(['POST'])
def save_draft(request):
    """Сохранить новый черновик письма."""
    to_val = request.POST.get('to', '')
    cc_val = request.POST.get('cc', '')
    bcc_val = request.POST.get('bcc', '')
    subject_val = request.POST.get('subject', '')
    body_val = request.POST.get('body', '')

    from django.conf import settings

    # Создаём директорию черновиков
    draft_dir = os.path.join(settings.DRAFT_DIRECTORY)
    os.makedirs(draft_dir, exist_ok=True)

    # Создаём уникальную поддиректорию для письма
    from datetime import datetime
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    subject_clean = subject_val[:50] if subject_val else 'no_subject'
    safe_subject = ''.join(c if c.isalnum() or c in ' -_.,()' else '_' for c in subject_clean).strip()
    email_dir = os.path.join(draft_dir, f'{ts}_{safe_subject}')
    os.makedirs(email_dir, exist_ok=True)

    # Сохраняем HTML тело
    if body_val:
        body_path = os.path.join(email_dir, f'{safe_subject}.html')
        with open(body_path, 'w', encoding='utf-8') as f:
            f.write(body_val)

    Email.objects.create(
        email_type='OUT',
        subject=subject_val,
        sender='',
        receiver=to_val,
        cc=cc_val,
        bcc=bcc_val,
        link=email_dir,
        folder='drafts',
        sent_status='draft',
    )

    return HttpResponse(status=204)


@login_required
@require_http_methods(['POST'])
def draft_update(request, pk):
    """Обновить существующий черновик (без отправки)."""
    draft = get_object_or_404(Email, pk=pk, folder='drafts')
    to_val = request.POST.get('to', '')
    cc_val = request.POST.get('cc', '')
    bcc_val = request.POST.get('bcc', '')
    subject_val = request.POST.get('subject', '')
    body_val = request.POST.get('body', '')

    draft.receiver = to_val
    draft.cc = cc_val
    draft.bcc = bcc_val
    draft.subject = subject_val
    draft.save(update_fields=['receiver', 'cc', 'bcc', 'subject'])

    # Обновляем HTML тело
    if draft.link:
        html_path = draft.get_html_file_path()
        if html_path:
            os.makedirs(os.path.dirname(html_path), exist_ok=True)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(body_val or '')

    return HttpResponse(status=204)


@login_required
@require_http_methods(['POST'])
def copy_to_draft(request, pk):
    """Дублировать письмо в черновики."""
    email = get_object_or_404(Email, pk=pk)
    next_url = _sanitize_next_url(request.POST.get('next', reverse('email_ui:inbox_default')))

    try:
        from django.conf import settings as django_settings
        draft_dir = os.path.join(django_settings.DRAFT_DIRECTORY)
        os.makedirs(draft_dir, exist_ok=True)

        ts = timezone.now().strftime('%Y%m%d_%H%M%S')
        subject_clean = (email.subject or 'no_subject')[:50]
        safe_subject = ''.join(c if c.isalnum() or c in ' -_.,()' else '_' for c in subject_clean).strip()
        email_dir = os.path.join(draft_dir, f'{ts}_{safe_subject}')
        os.makedirs(email_dir, exist_ok=True)

        if email.link and os.path.exists(email.link):
            from shutil import copytree
            copytree(email.link, email_dir, dirs_exist_ok=True)

        html_path = email.get_html_file_path()
        if html_path and os.path.exists(html_path):
            from shutil import copy2
            body_name = os.path.basename(html_path)
            copy2(html_path, os.path.join(email_dir, body_name))

        new_email = Email.objects.create(
            email_type='OUT',
            subject=email.subject,
            sender=email.sender,
            receiver=email.receiver,
            cc=email.cc,
            bcc=email.bcc,
            link=email_dir,
            folder='drafts',
            sent_status='draft',
            is_read=True,
            project_site=email.project_site,
            contractor=email.contractor,
            building_type=email.building_type,
            category=email.category,
            info=email.info,
            is_important=email.is_important,
        )

        for att in email.attachments.all():
            Attachment.objects.create(
                email=new_email,
                file_path=att.file_path,
                filename=att.filename,
                size=att.size,
                content_type=att.content_type,
            )

        messages.success(request, 'Письмо сохранено как черновик')
    except Exception as e:
        logger.exception(f'Ошибка дублирования в черновик: {e}')
        messages.error(request, f'Ошибка сохранения черновика: {e}')

    return redirect(next_url)


# ==================== Phase 7: Contact Management ====================

@login_required
def contact_list(request):
    """Список контактов."""
    query = request.GET.get('q', '')
    contacts = Contact.objects.filter(is_active=True)
    if query:
        contacts = contacts.filter(
            Q(name__icontains=query) | Q(emails__email__icontains=query)
        ).distinct()
    contacts = contacts.order_by('name')
    return render(request, 'email_ui/contacts/list.html', {
        'contacts': contacts,
        'query': query,
    })


@login_required
def contact_detail(request, pk):
    """Детальный просмотр контакта со всеми письмами."""
    contact = get_object_or_404(Contact, pk=pk)
    emails = Email.objects.filter(contact=contact).order_by('-email_stamp')[:50]
    return render(request, 'email_ui/contacts/detail.html', {
        'contact': contact,
        'emails': emails,
    })


@login_required
def contact_create_modal(request):
    """Модальное окно создания контакта."""
    form = ContactForm()
    email_form = ContactEmailForm()
    return render(request, 'email_ui/partials/contact_modal.html', {
        'form': form,
        'email_form': email_form,
        'mode': 'create',
    })


@login_required
@require_http_methods(['POST'])
def contact_create(request):
    """Создание контакта (AJAX)."""
    form = ContactForm(request.POST)
    email_form = ContactEmailForm(request.POST)
    if form.is_valid() and email_form.is_valid():
        contact = form.save()
        ContactEmail.objects.create(
            contact=contact,
            email=email_form.cleaned_data['email'],
            label=email_form.cleaned_data.get('label', 'work'),
            is_primary=True,
        )
        messages.success(request, f'Контакт "{contact.name}" создан')
        return HttpResponse(status=204)
    return render(request, 'email_ui/partials/contact_modal.html', {
        'form': form,
        'email_form': email_form,
        'mode': 'create',
    }, status=400)


@login_required
def contact_edit_modal(request, pk):
    """Модальное окно редактирования контакта."""
    contact = get_object_or_404(Contact, pk=pk)
    form = ContactForm(instance=contact)
    return render(request, 'email_ui/partials/contact_modal.html', {
        'form': form,
        'contact': contact,
        'mode': 'edit',
    })


@login_required
@require_http_methods(['POST'])
def contact_edit(request, pk):
    """Редактирование контакта (AJAX)."""
    contact = get_object_or_404(Contact, pk=pk)
    form = ContactForm(request.POST, instance=contact)
    if form.is_valid():
        form.save()
        messages.success(request, 'Контакт обновлён')
        return HttpResponse(status=204)
    return render(request, 'email_ui/partials/contact_modal.html', {
        'form': form,
        'contact': contact,
        'mode': 'edit',
    }, status=400)


@login_required
@require_http_methods(['POST'])
def contact_delete(request, pk):
    """Удаление контакта."""
    contact = get_object_or_404(Contact, pk=pk)
    contact.delete()
    messages.success(request, 'Контакт удалён')
    return redirect('email_ui:contact_list')


@login_required
def contact_search(request):
    """Поиск контактов для автодополнения (AJAX)."""
    query = request.GET.get('q', '')
    contacts = Contact.objects.filter(
        Q(name__icontains=query) | Q(emails__email__icontains=query)
    ).distinct()[:10]
    data = [{
        'id': c.id,
        'name': c.name,
        'email': c.primary_email.email if c.primary_email else (c.emails.first().email if c.emails.exists() else ''),
        'company': c.company.name if c.company else '',
    } for c in contacts]
    return JsonResponse(data, safe=False)


def _groups_picker_json(groups=None):
    """Группы для пикера: [{n: название, e: [твёрдые почты плоско]}]."""
    if groups is None:
        groups = ContactGroup.objects.filter(is_active=True).prefetch_related(
            'contacts__emails', 'subgroups',
        )
    return [{'n': g.name, 'e': g.all_emails()} for g in groups]


# ==================== Contact Groups ====================

def _safe_next(request, fallback_view, **kwargs):
    """Безопасный возврат к месту вызова (?next=) или fallback."""
    from django.utils.http import url_has_allowed_host_and_scheme
    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(
        nxt,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(nxt)
    return redirect(fallback_view, **kwargs)


@login_required
def group_list(request):
    """Список групп адресатов."""
    query = request.GET.get('q', '')
    groups = ContactGroup.objects.filter(is_active=True)
    if query:
        groups = groups.filter(
            Q(name__icontains=query)
            | Q(contacts__name__icontains=query)
            | Q(contacts__emails__email__icontains=query)
        ).distinct()
    return render(request, 'email_ui/groups/list.html', {
        'groups': groups.order_by('name'),
        'query': query,
    })


@login_required
def group_detail(request, pk):
    """Карточка группы: состав, вложенность, итоговые адреса."""
    group = get_object_or_404(ContactGroup, pk=pk)
    return render(request, 'email_ui/groups/detail.html', {
        'group': group,
        'all_emails': group.all_emails(),
        'free_contacts': Contact.objects.filter(is_active=True).order_by('name'),
        'free_groups': ContactGroup.objects.filter(
            is_active=True,
        ).exclude(pk=group.pk).order_by('name'),
        'next': request.GET.get('next', ''),
    })


@login_required
def group_create_modal(request):
    """Модальное окно создания группы."""
    return render(request, 'email_ui/partials/group_modal.html', {
        'form': ContactGroupForm(),
        'mode': 'create',
    })


@login_required
@require_http_methods(['POST'])
def group_create(request):
    """Создание группы (AJAX)."""
    form = ContactGroupForm(request.POST)
    if form.is_valid():
        group = form.save()
        messages.success(request, f'Группа "{group.name}" создана')
        return HttpResponse(status=204)
    return render(request, 'email_ui/partials/group_modal.html', {
        'form': form,
        'mode': 'create',
    }, status=400)


@login_required
def group_edit_modal(request, pk):
    """Модальное окно переименования группы."""
    group = get_object_or_404(ContactGroup, pk=pk)
    return render(request, 'email_ui/partials/group_modal.html', {
        'form': ContactGroupForm(instance=group),
        'group': group,
        'mode': 'edit',
    })


@login_required
@require_http_methods(['POST'])
def group_edit(request, pk):
    """Переименование группы (AJAX)."""
    group = get_object_or_404(ContactGroup, pk=pk)
    form = ContactGroupForm(request.POST, instance=group)
    if form.is_valid():
        form.save()
        messages.success(request, 'Группа обновлена')
        return HttpResponse(status=204)
    return render(request, 'email_ui/partials/group_modal.html', {
        'form': form,
        'group': group,
        'mode': 'edit',
    }, status=400)


@login_required
@require_http_methods(['POST'])
def group_delete(request, pk):
    """Удаление группы (сами контакты не трогает)."""
    group = get_object_or_404(ContactGroup, pk=pk)
    group.delete()
    messages.success(request, 'Группа удалена')
    return _safe_next(request, 'email_ui:group_list')


@login_required
@require_http_methods(['POST'])
def group_add_contact(request, pk):
    """Добавить контакт в группу."""
    group = get_object_or_404(ContactGroup, pk=pk)
    contact = get_object_or_404(Contact, pk=request.POST.get('contact_id'))
    group.contacts.add(contact)
    messages.success(request, f'{contact.name} добавлен в группу')
    return redirect('email_ui:group_detail', pk=group.pk)


@login_required
@require_http_methods(['POST'])
def group_remove_contact(request, pk):
    """Убрать контакт из группы."""
    group = get_object_or_404(ContactGroup, pk=pk)
    contact = get_object_or_404(Contact, pk=request.POST.get('contact_id'))
    group.contacts.remove(contact)
    messages.success(request, f'{contact.name} убран из группы')
    return redirect('email_ui:group_detail', pk=group.pk)


@login_required
@require_http_methods(['POST'])
def group_add_subgroup(request, pk):
    """Вложить группу в группу (с защитой от циклов)."""
    group = get_object_or_404(ContactGroup, pk=pk)
    sub = get_object_or_404(ContactGroup, pk=request.POST.get('subgroup_id'))
    if group.would_cycle(sub):
        messages.error(request, f'Нельзя вложить "{sub.name}": циклическая вложенность')
    else:
        group.subgroups.add(sub)
        messages.success(request, f'Группа "{sub.name}" вложена')
    return redirect('email_ui:group_detail', pk=group.pk)


@login_required
@require_http_methods(['POST'])
def group_remove_subgroup(request, pk):
    """Убрать вложенную группу."""
    group = get_object_or_404(ContactGroup, pk=pk)
    sub = get_object_or_404(ContactGroup, pk=request.POST.get('subgroup_id'))
    group.subgroups.remove(sub)
    messages.success(request, f'Группа "{sub.name}" убрана')
    return redirect('email_ui:group_detail', pk=group.pk)


# ==================== Phase 3: Tags ====================

@login_required
def tag_list(request):
    """Список всех тегов."""
    tags = EmailTag.objects.all()
    return render(request, 'email_ui/partials/tag_list.html', {'tags': tags})


@login_required
def tag_create_modal(request):
    """Модальное окно создания тега."""
    form = EmailTagForm()
    return render(request, 'email_ui/partials/tag_modal.html', {
        'form': form, 'mode': 'create',
    })


@login_required
@require_http_methods(['POST'])
def tag_create(request):
    """Создание тега (AJAX)."""
    form = EmailTagForm(request.POST)
    if form.is_valid():
        tag = form.save()
        messages.success(request, f'Тег "{tag.name}" создан')
        return HttpResponse(status=204)
    return render(request, 'email_ui/partials/tag_modal.html', {
        'form': form, 'mode': 'create',
    }, status=400)


@login_required
@require_http_methods(['POST'])
def tag_delete(request, pk):
    """Удаление тега."""
    tag = get_object_or_404(EmailTag, pk=pk)
    tag.delete()
    messages.success(request, f'Тег удалён')
    return HttpResponse(status=204)


@login_required
@require_http_methods(['POST'])
def assign_tag(request):
    """Назначить тег письму (AJAX)."""
    email_id = sanitize_id(request.POST.get('email_id'))
    tag_id = request.POST.get('tag_id')
    tag_name = request.POST.get('tag_name')

    email = get_object_or_404(Email, pk=email_id)

    if tag_id:
        tag = get_object_or_404(EmailTag, pk=tag_id)
    elif tag_name:
        tag, _ = EmailTag.objects.get_or_create(name=tag_name)
    else:
        return HttpResponseBadRequest('Не указан тег')

    link, created = EmailEmailTag.objects.get_or_create(
        email=email, tag=tag,
        defaults={'added_by': request.user},
    )

    return JsonResponse({
        'success': True,
        'created': created,
        'tag_name': tag.name,
        'tag_color': tag.color,
    })


@login_required
@require_http_methods(['POST'])
def remove_tag(request, email_id, tag_id):
    """Удалить тег с письма."""
    EmailEmailTag.objects.filter(email_id=email_id, tag_id=tag_id).delete()
    return HttpResponse(status=204)


@login_required
@require_http_methods(['POST'])
def bulk_assign_tag(request):
    """Массовое назначение тега письмам."""
    raw_ids = request.POST.getlist('email_ids')
    email_ids = sanitize_id_list(raw_ids)
    tag_id = request.POST.get('tag_id')

    if not email_ids or not tag_id:
        return HttpResponseBadRequest('Не указаны письма или тег')

    tag = get_object_or_404(EmailTag, pk=sanitize_id(tag_id))
    emails = Email.objects.filter(id__in=email_ids)

    for email in emails:
        EmailEmailTag.objects.get_or_create(
            email=email, tag=tag,
            defaults={'added_by': request.user},
        )

    messages.success(request, f'Тег "{tag.name}" назначен {emails.count()} письмам')
    return HttpResponse(status=204)


# ==================== Phase 4: Email ↔ Task ====================

@login_required
@require_http_methods(['POST'])
def link_email_to_task(request):
    """Связать письмо с задачей (AJAX)."""
    email_id = sanitize_id(request.POST.get('email_id'))
    task_id = sanitize_id(request.POST.get('task_id'))
    link_type = request.POST.get('link_type', 'related')

    link, created = EmailTaskLink.objects.get_or_create(
        email_id=email_id,
        task_node_id=task_id,
        defaults={
            'link_type': link_type,
            'created_by': request.user,
        },
    )

    return JsonResponse({
        'success': True,
        'created': created,
        'link_id': link.id,
        'task_name': link.task_node.name,
    })


@login_required
@require_http_methods(['POST'])
def unlink_email_from_task(request, link_id):
    """Удалить связь письма с задачей."""
    link = get_object_or_404(EmailTaskLink, pk=link_id)
    link.delete()
    return HttpResponse(status=204)


@login_required
@require_http_methods(['POST'])
def copy_email(request, pk):
    """Скопировать письмо в структуру проекта (как в админке)."""
    email = get_object_or_404(Email, pk=pk)
    next_url = request.POST.get('next', reverse('email_ui:email_detail', args=[pk]))
    if not email.project_site or not email.contractor:
        messages.error(request, 'Для копирования нужно указать проект и подрядчика')
        return redirect(next_url)

    try:
        from shutil import copytree
        from datetime import datetime
        from django.utils.text import slugify

        email_type = getattr(EmailType, email.email_type).value
        year = str(datetime.today().year)
        today = datetime.today().strftime('%Y_%m_%d')
        folder_name = email.name if email.name else slugify(email.subject)[:50]
        _directory = os.path.join(
            E_MAIL_DIRECTORY,
            email.project_site.name,
            email.contractor.name,
            email_type,
            year,
            f'{today}_{folder_name}',
        )
        os.makedirs(_directory, exist_ok=True)
        if email.link and os.path.exists(email.link):
            copytree(email.link, _directory, dirs_exist_ok=True)
        if os.path.exists(_directory):
            try:
                import win32clipboard
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(_directory, win32clipboard.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
            except Exception:
                pass
            messages.success(request, f'Файлы скопированы в папку {_directory}')
        else:
            messages.error(request, f'Директория не создана: {_directory}')
    except Exception as e:
        messages.error(request, f'Ошибка копирования: {e}')

    return redirect(next_url)


@login_required
def create_task_from_email(request, pk):
    """Создать задачу (TaskNode) из письма."""
    email = get_object_or_404(Email, pk=pk)
    if request.method == 'POST':
        from ProjectTDL.forms import TaskForm
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.owner = request.user
            task.node_type = 'task'
            task.save()
            EmailTaskLink.objects.create(
                email=email,
                task_node=task,
                link_type='created_from',
                created_by=request.user,
            )
            messages.success(request, f'Задача "{task.name}" создана из письма')
            next_url = request.POST.get('next', reverse('email_ui:email_detail', args=[pk]))
            return redirect(next_url)
    else:
        from ProjectTDL.forms import TaskForm
        initial = {
            'name': f'По письму: {email.subject}',
        }
        form = TaskForm(initial=initial)

    return render(request, 'email_ui/partials/create_task_form.html', {
        'form': form,
        'email': email,
    })


# ==================== Phase 6: Export ====================

@login_required
def export_modal(request):
    """Модальное окно экспорта писем."""
    form = ExportForm()
    return render(request, 'email_ui/partials/export_modal.html', {'form': form})


@login_required
@require_http_methods(['POST'])
def do_export(request):
    """Выполнить экспорт выбранных писем."""
    raw_ids = request.POST.getlist('selected_emails')
    email_ids = sanitize_id_list(raw_ids)
    form = ExportForm(request.POST)

    if not email_ids or not form.is_valid():
        return HttpResponseBadRequest('Не выбраны письма или форма невалидна')

    cd = form.cleaned_data
    base_path = E_MAIL_DIRECTORY
    export_path = os.path.join(base_path, 'exports', f'export_{timezone.now():%Y%m%d_%H%M%S}')

    from .services.export_service import EmailExportService
    results = EmailExportService.export_selected(
        email_ids=email_ids,
        export_path=export_path,
        format=cd['export_format'],
        include_attachments=cd.get('include_attachments', True),
        organize_by=cd['organize_by'],
    )

    messages.success(request, f'Экспортировано: {results["exported"]}, ошибок: {results["failed"]}')
    return redirect(reverse('email_ui:inbox_default'))


# ==================== Phase 3: Saved Filters ====================

@login_required
def saved_filters_list(request):
    """Список сохранённых фильтров."""
    filters = SavedFilter.objects.filter(Q(user=request.user) | Q(is_shared=True))
    return render(request, 'email_ui/partials/saved_filters_list.html', {'filters': filters})


@login_required
@require_http_methods(['POST'])
def save_current_filter(request):
    """Сохранить текущий фильтр."""
    form = SavedFilterForm(request.POST)
    if form.is_valid():
        sf = form.save(commit=False)
        sf.user = request.user
        # Store the current GET parameters as the filter
        sf.filters = dict(request.GET.lists())
        sf.save()
        messages.success(request, f'Фильтр "{sf.name}" сохранён')
        return HttpResponse(status=204)
    return render(request, 'email_ui/partials/saved_filter_form.html', {
        'form': form, 'mode': 'save',
    }, status=400)


@login_required
@require_http_methods(['POST'])
def apply_saved_filter(request, pk):
    """Применить сохранённый фильтр."""
    sf = get_object_or_404(SavedFilter, pk=pk, user=request.user)
    # Build URL with filter params
    from urllib.parse import urlencode
    params = {}
    for key, values in sf.filters.items():
        if len(values) == 1:
            params[key] = values[0]
        else:
            params[key] = values
    url = f"{reverse('email_ui:inbox_default')}?{urlencode(params, doseq=True)}"
    return redirect(url)


@login_required
@require_http_methods(['POST'])
def delete_saved_filter(request, pk):
    """Удалить сохранённый фильтр."""
    sf = get_object_or_404(SavedFilter, pk=pk, user=request.user)
    sf.delete()
    return HttpResponse(status=204)


# ==================== Phase 8: Automation Rules ====================

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
    if form.is_valid():
        rule = form.save(commit=False)
        rule.created_by = request.user
        rule.save()
        messages.success(request, f'Правило "{rule.name}" создано')
        return HttpResponse(status=204)
    return render(request, 'email_ui/partials/rule_modal.html', {
        'form': form, 'mode': 'create',
    }, status=400)


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
    if form.is_valid():
        form.save()
        messages.success(request, 'Правило обновлено')
        return HttpResponse(status=204)
    return render(request, 'email_ui/partials/rule_modal.html', {
        'form': form, 'rule': rule, 'mode': 'edit',
    }, status=400)


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
    """Запустить правило для всех писем."""
    rule = get_object_or_404(EmailRule, pk=pk)
    from .services.rule_engine import RuleEngine
    engine = RuleEngine()
    count = engine.process_emails(Email.objects.all())
    messages.success(request, f'Правило "{rule.name}" применено к {count} письмам')
    return HttpResponse(status=204)


# ==================== Threading ====================

@login_required
def email_thread(request, pk):
    """Просмотр цепочки писем."""
    email = get_object_or_404(Email, pk=pk)
    from .services.thread_service import ThreadService
    thread = ThreadService.get_thread(email)
    _attach_thread_context(thread)
    return render(request, 'email_ui/partials/email_thread.html', {
        'thread': thread,
        'active_email': email,
    })
