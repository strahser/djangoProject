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
    ComposeEmailForm, ComposeReplyForm,
    EmailFilterForm, EmailMetadataForm,
    ExportForm,
)
from .models import (
    EmailTag, EmailTaskLink, EmailTemplate, EmailViewSettings, SavedFilter,
)
from .services.email_sender import EmailSenderService
from .services import email_tasks as email_tasks_service
from .utils import (
    append_disk_links_html, clean_email_html, resolve_sender_to_email,
    quote_body_html,
    resolve_inline_image_urls, sanitize_id, sanitize_id_list, segment_letter_html,
)
from .services.navigation import (
    ALLOWED_SORT_FIELDS, _build_back_url, _clean_query_string,
    _get_list_from_request, _safe_next, _sanitize_next_url, apply_sorting,
    # ALLOWED_SORT_FIELDS/_safe_next — намеренные ре-экспорты:
    # tests_views_b25 тянет их из views (контракт блока 25).
)
from .services.seen_sync import push_seen_async
from .services.query_service import (
    SEARCH_ANYWHERE_FIELDS, _ci_variants, _field_tokens, _q_field_variants,
    _q_token_anywhere, _query_tokens, _split_tokens, _token_addresses,
    filter_emails, highlight_words,
)
from .services.compose_flow import (
    active_contacts, collect_reply_attachments,
    contacts_picker_json as _contacts_picker_json,
    current_user_email,
    groups_picker_json as _groups_picker_json,
    prepare_draft_dir, record_draft_attachments,
    reply_all_recipients as _reply_all_recipients,
    resolve_reply_recipients, resolve_subject,
)
from .services.thread_service import (
    attach_thread_context as _attach_thread_context,
    attach_thread_page_heads as _attach_thread_page_heads,
    build_selection_threads as _build_selection_threads,
    build_thread_list as _build_thread_list,
)
PER_PAGE = 50
THREADS_PER_PAGE = 20


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
    # Счётчик для бейджа на кнопке «Фильтры и поиск»: пустые значения
    # (search=, search_scope= в поделившейся ссылке) фильтрами не считаем.
    _count_keys = ('search', 'sender', 'receiver', 'cc', 'attachment_name', 'date_from', 'date_to',
                   'sent_status', 'has_attachments', 'has_disk_links', 'is_important', 'is_unread', 'in_files')
    active_filter_count = sum(
        1 for k in _count_keys if (request.GET.get(k) or '').strip()
    ) + sum(
        1 for k in ('project_site', 'contractor', 'building_type',
                    'category', 'info', 'tags')
        for v in request.GET.getlist(k) if str(v).strip()
    )
    context = {
        'folder': folder,
        'page_obj': page_obj,
        'filter_form': filter_form,
        'total_count': paginator.count,        'current_sort': current_sort,
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
        'active_filter_count': active_filter_count,
        'hl_tokens': highlight_words(request.GET.get('search', '')),
        'pinned_filters': SavedFilter.objects.filter(
            Q(user=request.user) | Q(is_shared=True),
            is_pinned=True).order_by('name'),
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
            'folder': folder,
            'page_obj': page_obj,
            'clean_params': _clean_query_string(request),
            'email_list_back_url': _build_back_url(request, folder),
            'active_filters': active_filters,
            'hl_tokens': highlight_words(request.GET.get('search', '')),
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
        'hl_tokens': highlight_words(request.GET.get('search', '')),
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
        push_seen_async(email, seen=True)

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
        push_seen_async(email, seen=True)

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
        push_seen_async(email, seen=True)
    return HttpResponse(status=204)  # No content, успешно


@login_required
def email_body(request, pk):
    """Возвращает очищенный HTML письма в «бумажной» карточке с переключателем режимов."""
    email = get_object_or_404(Email, pk=pk)
    html_path = email.get_html_file_path()

    def _frame(inner: str, disk: str = '') -> str:
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
            f'<div class="letter-content">{inner}</div>{disk}</div>'
        )

    def _disk_block() -> str:
        # Ссылки Яндекс.Диска — отдельным блоком после рамки, а не в хвосте
        # контента (там они тонули в зоне цитат). Показываем, даже если
        # самого тела нет: файл ссылок живёт отдельно.
        # Заодно самолечение флага has_disk_links (для фильтра): правим,
        # только если в БД другое значение.
        disk = clean_email_html(append_disk_links_html(email, ''))
        has = bool(disk.strip())
        if email.has_disk_links != has:
            try:
                email.has_disk_links = has
                email.save(update_fields=['has_disk_links'])
            except Exception:
                pass
        if not has:
            return ''
        return (
            '<div class="letter-section letter-disk">'
            '<div class="letter-section-title"><i class="bi bi-cloud-arrow-down me-1"></i>Файлы на Яндекс.Диске</div>'
            f'<div class="letter-section-body">{disk}</div></div>'
        )

    if not html_path or not os.path.exists(html_path):
        return HttpResponse(_frame('<p class="text-muted">Файл письма не найден</p>', _disk_block()))
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            raw_html = f.read()
        resolved = resolve_inline_image_urls(email, raw_html)
        cleaned = clean_email_html(resolved)
        segmented = segment_letter_html(cleaned)
        return HttpResponse(_frame(segmented, _disk_block()))
    except Exception as e:
        return HttpResponse(_frame(f'<p>Ошибка загрузки: {e}</p>'))


@login_required
def serve_inline_attachment(request, att_id):
    """Отдаёт вложение inline — для картинок, встроенных в тело письма."""
    att = get_object_or_404(Attachment, pk=att_id)
    path = att.resolved_path
    if not os.path.exists(path):
        raise Http404("Файл не найден")
    content_type, encoding = mimetypes.guess_type(att.filename)
    if not content_type:
        content_type = att.content_type or 'application/octet-stream'
    response = FileResponse(open(path, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'inline; filename="{att.filename}"'
    return response


@login_required
def download_attachment(request, att_id):
    """Скачивание вложения."""
    att = get_object_or_404(Attachment, pk=att_id)
    path = att.resolved_path
    if not os.path.exists(path):
        raise Http404("Файл не найден")
    content_type, encoding = mimetypes.guess_type(att.filename)
    if not content_type:
        content_type = 'application/octet-stream'
    response = FileResponse(open(path, 'rb'), content_type=content_type)
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
        os.makedirs(os.path.dirname(email.resolved_link or ''), exist_ok=True)
        link_dir = email.resolved_link
        if link_dir:
            file_path = os.path.join(link_dir, uploaded_file.name)
            with open(file_path, 'wb+') as dest:
                for chunk in uploaded_file.chunks():
                    dest.write(chunk)
            att.file_path = file_path
            att.save(update_fields=['file_path'])
            try:
                from .services.file_text import index_attachment
                index_attachment(att)
            except FileNotFoundError:
                pass
            except Exception:
                pass
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
            f'<button class="btn btn-sm {btn_class}" id="star-btn" hx-post="{reverse("email_ui:toggle_important", args=[pk])}" '
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
    # Синхронизируем вторую связь (EmailTaskLink), иначе в админском inline
    # письмо оставалось привязанным к задаче после отвязки.
    EmailTaskLink.objects.filter(email=email, task_node=task).delete()
    message = f'Задача «{task.name[:40]}» отвязана от письма'
    return HttpResponse(
        f'<script>showToast({json.dumps(message)}, "info")</script>'
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
        push_seen_async(list(emails.only('id', 'uid', 'folder')), seen=True)
    elif action == 'mark_unread':
        emails.update(is_read=False)
        push_seen_async(list(emails.only('id', 'uid', 'folder')), seen=False)
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
            'hl_tokens': highlight_words(filter_qd.get('search', '') if filter_params else ''),
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


@login_required
@require_http_methods(['POST'])
def fetch_emails(request):
    """
    Запускает процесс получения почты через IMAP.
    После завершения редиректит обратно на страницу, с которой пришёл запрос.
    """
    # Количество писем для загрузки (по умолчанию 10). Мусор в поле —
    # дефолт, а не 500 (было int() без валидации).
    try:
        email_limit = int(request.POST.get('mail_count', 10))
    except (ValueError, TypeError):
        email_limit = 10
    email_limit = min(max(email_limit, 1), 500)

    # Соответствие папок IMAP и внутренних типов
    initial_folder_list = {
        'INBOX': EmailType.IN.name,
        'Отправленные': EmailType.OUT.name
    }

    actions_list = []  # Успешно обработанные
    scip_list = []  # Пропущенные (уже есть)
    error_list = []  # Ошибки соединения/обработки по папкам

    # Базовая директория для сохранения вложений
    directory = os.path.join(E_MAIL_DIRECTORY, 'imap_attachments')

    for folder, folder_db_name in initial_folder_list.items():
        root_path = os.path.join(directory, folder)
        try:
            parser = ParsingImapEmailToDB(root_path)
            parser.main(folder_db_name, folder, limit=email_limit)
        except Exception as e:
            # Падение одной папки (обрыв IMAP, нет папки на сервере) не
            # роняет вторую: факт — в error_list, пользователь видит warning.
            logger.exception(f'IMAP ({folder}): получение не удалось: {e}')
            error_list.append(f'{folder}: {e}')
            continue
        actions_list.append(parser.create_action_list)
        scip_list.append(parser.skip_action_list)
        error_list.extend(parser.error_list)

    # Преобразуем списки списков в плоский список
    actions_list = flatten(actions_list)
    scip_list = flatten(scip_list)

    if actions_list:
        res_list = [str(val) for val in actions_list]
        messages.success(request, f"Почта сохранена для следующих позиций: {', '.join(res_list)}")
    else:
        messages.info(request, "Новых писем не найдено")
    if error_list:
        # Транзиентный обрыв Яндекса (BYE problems with connection):
        # пользователь должен видеть, что папка пропущена, а не тишину.
        messages.warning(
            request,
            "Не все папки проверены (сервер временно разорвал соединение, "
            "следующая загрузка доберёт пропущенное): "
            + "; ".join(str(e) for e in error_list[:5]),
        )

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
    folder_path = email.resolved_link
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


# ==================== Phase 2: Compose & Send ====================

@login_required
@require_http_methods(['GET'])
def template_list(request):
    """Список шаблонов быстрых ответов для композера (id+name)."""
    items = list(EmailTemplate.objects.order_by('name').values('id', 'name'))
    return JsonResponse({'templates': items})


@login_required
@require_http_methods(['GET'])
def template_render(request, pk):
    """Рендер шаблона для вставки в композер: переменные — значениями
    по умолчанию (незаполненные Django гасит в '')."""
    tpl = get_object_or_404(EmailTemplate, pk=pk)
    from django.template import Context, Template
    ctx = Context({v.name: v.default_value for v in tpl.variables.all()})
    return JsonResponse({
        'subject': Template(tpl.subject_template).render(ctx),
        'body': Template(tpl.body_template).render(ctx),
    })


@login_required
def compose_modal(request):
    """Редактор для создания нового письма."""
    form = ComposeEmailForm()
    contacts = active_contacts()
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

    # Подгружаем тело исходного письма для цитирования: чистим (сырой HTML
    # со стилями/скриптами в редактор нельзя) и обрезаем до сути
    # (без шапок, старых цитат и подписей) с заголовком «автор, дата».
    body_text = ''
    load_original = reply_type in ('reply', 'reply_all', 'forward')
    if load_original:
        html_path = email.get_html_file_path()
        if html_path and os.path.exists(html_path):
            try:
                with open(html_path, 'r', encoding='utf-8') as f:
                    orig = f.read()
                    quoted = quote_body_html(clean_email_html(orig))
                    if quoted.strip():
                        from django.utils.html import escape as _escape
                        stamp = (email.email_stamp.strftime('%d.%m.%Y %H:%M')
                                 if getattr(email, 'email_stamp', None) else '')
                        head = f'{stamp} {email.sender or ""} писал:'.strip()
                        body_text = (f'<br><hr><p><em>{_escape(head)}</em></p>'
                                     f'<blockquote>{quoted}</blockquote>')
            except Exception:
                pass

    to_addr = ''
    cc_addr = ''
    resolve_errors = []
    user_email = current_user_email(request)

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

    contacts = active_contacts()
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
    contacts = active_contacts()
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

    from email_ui.services import compose_service as compose

    cd = form.cleaned_data

    try:
        uploaded_files = request.FILES.getlist('attachment_files')

        # Send
        sender = compose.build_sender(cd)

        to_list = compose.parse_recipients(cd['to'])
        bad = compose.invalid_addresses(to_list)
        if bad:
            form.add_error('to', f'Некорректные адреса: {", ".join(bad)}')
            return render(request, 'email_ui/partials/compose_modal.html', {
                'form': form, 'mode': 'compose', 'contacts': contacts,
                'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
            }, status=400)

        cc_list = compose.parse_recipients(cd.get('cc', ''))
        bcc_list = compose.parse_recipients(cd.get('bcc', ''))

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
            email_obj = compose.create_sent_email(
                sender=sender, subject=cd['subject'], to_list=to_list,
                cc_list=cc_list, bcc_list=bcc_list)
            # Save uploaded files to disk and create Attachment records
            compose.persist_uploaded_files(email_obj, uploaded_files)

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
    from email_ui.services import compose_service as compose

    email = get_object_or_404(Email, pk=pk)
    mode = request.POST.get('mode', 'reply')
    contacts = active_contacts()
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

    # Формируем получателей (фолбэки + чистка — в compose_flow).
    to_list, cc_list = resolve_reply_recipients(
        email, cd.get('to', ''), cd.get('cc', ''), mode,
        current_user_email(request))
    if not to_list:
        return render(request, 'email_ui/partials/compose_modal.html', {
            'form': form, 'email': email, 'mode': mode, 'contacts': contacts,
            'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
            'error': 'Не указан ни один действительный email получателя. '
                     'Укажите адрес вручную перед отправкой ответа.',
        }, status=400)

    subject = resolve_subject(email.subject, cd.get('subject', ''), mode)

    # Collect excluded attachment IDs from form
    excluded_ids = compose.parse_excluded_ids(request.POST)

    # Determine which attachments to forward
    include_attachments = cd.get('include_attachments', False) or mode == 'forward'
    attachment_objs = collect_reply_attachments(
        email, include_attachments, excluded_ids,
        request.FILES.getlist('attachment_files'))

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
        new_email = compose.create_sent_email(
            sender=sender, subject=subject, to_list=to_list, cc_list=cc_list,
            in_reply_to=email.message_id if mode != 'forward' else None,
            thread_id=email.thread_id if mode != 'forward' else None)

        # Save forwarded attachments to DB
        if include_attachments:
            compose.copy_attachment_rows(
                new_email, email.attachments.all(), excluded_ids)

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
    # Черновики, созданные через API (реестр М1 и др.), хранят тело в body_text
    # и не имеют HTML-файла — без фолбэка редактор открывался пустым.
    if not body_text:
        body_text = email.body_text or ''

    contacts = active_contacts()

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
        'bcc': email.bcc or '',
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
    from email_ui.services import compose_service as compose

    draft = get_object_or_404(Email, pk=pk, folder='drafts')
    contacts = active_contacts()
    form = ComposeEmailForm(request.POST, request.FILES)

    if not form.is_valid():
        return render(request, 'email_ui/draft_edit.html', {
            'form': form, 'mode': 'edit_draft', 'draft_email': draft,
            'draft_attachments': list(draft.attachments.all()),
            'to': draft.receiver or '', 'cc': draft.cc or '',
            'subject': draft.subject or '',
            'body': request.POST.get('body', ''),
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
            'subject': draft.subject or '',
            'body': request.POST.get('body', ''),
            'contacts': contacts,
            'contacts_json': _contacts_picker_json(contacts),
            'groups_json': _groups_picker_json(),
        }, status=400)

    try:
        uploaded_files = request.FILES.getlist('attachment_files')

        sender = compose.build_sender(cd)

        to_list = compose.parse_recipients(cd['to'])

        bad = compose.invalid_addresses(to_list)
        if bad:
            form.add_error('to', f'Некорректные адреса: {", ".join(bad)}')
            # BUG: шаблон compose_modal вместо draft_edit (расхождение UX-ошибок
            # тройника). Сохранено 1:1, фиксировать — решением владельца.
            return render(request, 'email_ui/partials/compose_modal.html', {
                'form': form, 'mode': 'edit_draft', 'draft_email': draft,
                'draft_attachments': list(draft.attachments.all()),
                'contacts': contacts,
                'contacts_json': _contacts_picker_json(contacts),
                'groups_json': _groups_picker_json(),
            }, status=400)

        cc_list = compose.parse_recipients(cd.get('cc', ''))
        bcc_list = compose.parse_recipients(cd.get('bcc', ''))

        # Собираем вложения: черновика (не удалённые) + новые загруженные
        excluded_ids = compose.parse_excluded_ids(request.POST)

        attachment_objs = collect_reply_attachments(
            draft, True, excluded_ids, uploaded_files)

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
            email_obj = compose.create_sent_email(
                sender=sender, subject=cd['subject'], to_list=to_list,
                cc_list=cc_list, bcc_list=bcc_list)

            # Сохраняем вложения отправленного письма в БД
            record_draft_attachments(email_obj, attachment_objs)

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
            'subject': draft.subject or '',
            'body': request.POST.get('body', ''),
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

    email_dir = prepare_draft_dir(subject_val, body_val)

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
def autosave_draft(request):
    """Тихое автосохранение черновика из композера (create-or-update, JSON).

    Первый вызов без draft_id создаёт черновик и возвращает его id —
    дальше клиент шлёт draft_id и черновик обновляется, а не множится.
    Пустое содержимое (нечего терять) — пропуск без создания.
    """
    draft = None
    draft_id = (request.POST.get('draft_id') or '').strip()
    if draft_id.isdigit():
        draft = Email.objects.filter(pk=int(draft_id), folder='drafts').first()
    to_val = request.POST.get('to', '')
    cc_val = request.POST.get('cc', '')
    bcc_val = request.POST.get('bcc', '')
    subject_val = request.POST.get('subject', '')
    body_val = request.POST.get('body', '')
    if draft is None and not any((v or '').strip() for v in (to_val, subject_val, body_val)):
        return JsonResponse({'id': None, 'skipped': True})
    if draft is None:
        from .services.compose_flow import prepare_draft_dir as _prepare_draft_dir
        draft = Email.objects.create(
            email_type='OUT',
            subject=subject_val,
            sender='',
            receiver=to_val,
            cc=cc_val,
            bcc=bcc_val,
            body_text=body_val,
            link=_prepare_draft_dir(subject_val, body_val),
            folder='drafts',
            sent_status='draft',
        )
    else:
        draft.receiver = to_val
        draft.cc = cc_val
        draft.bcc = bcc_val
        draft.subject = subject_val
        draft.body_text = body_val
        draft.save(update_fields=['receiver', 'cc', 'bcc', 'subject', 'body_text'])
        html_path = draft.get_html_file_path()
        if html_path:
            try:
                os.makedirs(os.path.dirname(html_path), exist_ok=True)
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(body_val or '')
            except OSError:
                pass
    return JsonResponse({'id': draft.pk})


@login_required
@require_http_methods(['POST'])
def draft_update(request, pk):
    """Обновить существующий черновик (без отправки)."""
    draft = get_object_or_404(Email, pk=pk, folder='drafts')

    # Полей to/cc/bcc в форме draft_edit нет — обновляем только те поля,
    # что реально пришли в POST, иначе каждое сохранение затирало бы
    # получателей пустыми строками.
    updated = []
    for field, key in (('receiver', 'to'), ('cc', 'cc'), ('bcc', 'bcc'), ('subject', 'subject')):
        if key in request.POST:
            setattr(draft, field, request.POST.get(key, ''))
            updated.append(field)

    # Тело — всегда в body_text БД; в HTML-файл — если есть куда писать.
    # Раньше тело писалось только в HTML (которого у API-черновиков нет),
    # и правки молча терялись.
    if 'body' in request.POST:
        draft.body_text = request.POST.get('body', '')
        updated.append('body_text')

    # У черновика может не быть link-каталога (старые/копированные черновики) —
    # создаём, иначе тело письма негде хранить и оно молча теряется.
    if not draft.link:
        from django.conf import settings
        draft_dir = os.path.join(settings.DRAFT_DIRECTORY)
        os.makedirs(draft_dir, exist_ok=True)
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        subject_clean = (draft.subject or '')[:50] or 'no_subject'
        safe_subject = ''.join(c if c.isalnum() or c in ' -_.,()' else '_' for c in subject_clean).strip()
        draft.link = os.path.join(draft_dir, f'{ts}_{safe_subject}')
        updated.append('link')
    if updated:
        draft.save(update_fields=updated)

    # Обновляем HTML тело (если есть куда писать)
    html_path = draft.get_html_file_path()
    if html_path:
        os.makedirs(os.path.dirname(html_path), exist_ok=True)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(draft.body_text or '')

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

        if email.resolved_link and os.path.exists(email.resolved_link):
            from shutil import copytree
            copytree(email.resolved_link, email_dir, dirs_exist_ok=True)

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
                file_path=att.resolved_path,
                filename=att.filename,
                size=att.size,
                content_type=att.content_type,
            )

        messages.success(request, 'Письмо сохранено как черновик')
    except Exception as e:
        logger.exception(f'Ошибка дублирования в черновик: {e}')
        messages.error(request, f'Ошибка сохранения черновика: {e}')

    return redirect(next_url)


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
        if email.resolved_link and os.path.exists(email.resolved_link):
            copytree(email.resolved_link, _directory, dirs_exist_ok=True)
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


def _email_tasks_htmx(request, email, message=None, level='success'):
    """Ответ для HTMX: обновлённый блок «Задачи письма» + тост."""
    from django.template.loader import render_to_string
    email = Email.objects.prefetch_related('tasks').get(pk=email.pk)
    html = render_to_string(
        'email_ui/partials/email_tasks_body.html',
        {'email': email}, request=request,
    )
    # Счётчик в заголовке секции (если он есть на странице) — OOB-свап.
    html = (f'<span id="email-tasks-count-{email.pk}" hx-swap-oob="true">'
            f'{email.tasks.count()}</span>' + html)
    if message:
        html += (f'<script>showToast({json.dumps(message)}, '
                 f'"{level}")</script>')
    return HttpResponse(html)


@login_required
@require_http_methods(['POST'])
def create_task_from_email(request, pk):
    """Превратить письмо в задачу: создать TaskNode и сразу прикрепить письмо.

    Раньше кнопка вела в админку на полную форму TaskNode: связь письма
    терялась (шаблон не выводил _email_id), а задача не появлялась в блоке
    «Задачи письма» (он читает email.tasks, а не EmailTaskLink). Теперь одно
    действие: задача + email.tasks.add + EmailTaskLink. Общая логика с
    действием правил create_task — email_ui/services/email_tasks.py.
    """
    email = get_object_or_404(Email, pk=pk)
    is_htmx = request.headers.get('HX-Request') == 'true'

    try:
        task, created = email_tasks_service.create_task_from_email(
            email, request.user)
    except ValueError as exc:
        message = f'Нельзя создать задачу: {exc}.'
        if is_htmx:
            return _email_tasks_htmx(request, email, message, 'error')
        messages.warning(request, message)
        return _safe_next(request, 'email_ui:email_detail', pk=pk)

    if created:
        message = f'Письмо превращено в задачу «{task.name}»'
    else:
        message = f'Задача «{task.name}» уже создана из этого письма'

    if is_htmx:
        return _email_tasks_htmx(
            request, email, message, 'success' if created else 'info')
    if created:
        messages.success(request, message)
    else:
        messages.info(request, message)
    return _safe_next(request, 'email_ui:email_detail', pk=pk)


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
