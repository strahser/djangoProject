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
from ProjectTDL.models import Task
from StaticData.models import BuildingType, Category, ProjectSite

from .forms import (
    ComposeEmailForm, ComposeReplyForm, ContactEmailForm, ContactForm,
    EmailFilterForm, EmailMetadataForm, EmailRuleForm, EmailTagForm,
    ExportForm, SavedFilterForm, TaskSearchForm,
)
from .models import (
    Contact, ContactEmail, EmailAutomationLog, EmailEmailTag, EmailRule,
    EmailTag, EmailTaskLink, EmailTemplate, SavedFilter, SMTPAccount,
)
from .services.email_sender import EmailSenderService
from .utils import clean_email_html, sanitize_id, sanitize_id_list
PER_PAGE = 50
# Разрешённые поля для сортировки

ALLOWED_SORT_FIELDS = ['sender', 'subject', 'email_stamp', 'project_site__name', 'contractor__name']


def apply_sorting(queryset, request):
    sort_field = request.GET.get('sort', 'email_stamp')
    sort_order = request.GET.get('order', 'desc')

    if sort_field.lstrip('-') not in ALLOWED_SORT_FIELDS:
        sort_field = 'email_stamp'

    if sort_order == 'desc' and not sort_field.startswith('-'):
        sort_field = f'-{sort_field}'

    return queryset.order_by(sort_field), sort_field.lstrip('-'), sort_order


def filter_emails(queryset, cleaned_data):
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
    if cleaned_data.get('date_from'):
        queryset = queryset.filter(email_stamp__date__gte=cleaned_data['date_from'])
    if cleaned_data.get('date_to'):
        queryset = queryset.filter(email_stamp__date__lte=cleaned_data['date_to'])
    if cleaned_data.get('folder'):
        queryset = queryset.filter(folder=cleaned_data['folder'])
    if cleaned_data.get('sent_status'):
        queryset = queryset.filter(sent_status=cleaned_data['sent_status'])
    if cleaned_data.get('search'):
        query = cleaned_data['search']
        queryset = queryset.filter(
            Q(subject__icontains=query) |
            Q(sender__icontains=query) |
            Q(receiver__icontains=query) |
            Q(name__icontains=query)
        )
    return queryset


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
    }
    return render(request, 'email_ui/inbox.html', context)


@login_required
@require_http_methods(['GET'])
def email_list_partial(request):
    """Частичное обновление списка писем."""
    folder = request.GET.get('folder', 'inbox')
    emails = Email.objects.filter(folder=folder).select_related(
        'project_site', 'contractor'
    ).prefetch_related('attachments')

    filter_form = EmailFilterForm(request.GET)
    if filter_form.is_valid():
        emails = filter_emails(emails, filter_form.cleaned_data)

    emails, current_sort, current_order = apply_sorting(emails, request)

    paginator = Paginator(emails, PER_PAGE)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Если запрос от индикатора бесконечной прокрутки – возвращаем только строки и новый индикатор
    if request.GET.get('_infinite'):
        context = {
            'page_obj': page_obj,
        }
        return render(request, 'email_ui/partials/email_rows.html', context)

    # Обычный запрос (первая загрузка, сортировка, фильтрация) – возвращаем полную таблицу
    context = {
        'folder': folder,
        'page_obj': page_obj,
        'current_sort': current_sort,
        'current_order': current_order,
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
    }
    return render(request, 'email_ui/partials/filter_form.html', context)


@login_required
def email_detail_modal(request, pk):
    """Возвращает фрагмент с деталями письма для модального окна."""
    email = get_object_or_404(
        Email.objects.select_related(
            'project_site', 'contractor', 'category', 'building_type'
        ).prefetch_related('attachments', 'tasks'),
        pk=pk
    )
    # Удалено: помечание прочитанным сразу при открытии
    # if not email.is_read:
    #     email.is_read = True
    #     email.save(update_fields=['is_read'])

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
    """Возвращает очищенное HTML-содержимое письма из файла."""
    email = get_object_or_404(Email, pk=pk)
    html_path = email.get_html_file_path()
    if not html_path or not os.path.exists(html_path):
        return HttpResponse('<p>Файл письма не найден</p>')
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            raw_html = f.read()
        cleaned = clean_email_html(raw_html)
        return HttpResponse(cleaned)
    except Exception as e:
        return HttpResponse(f'<p>Ошибка загрузки: {e}</p>')


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
        form.save()
        return render(request, 'email_ui/partials/metadata_display.html', {'email': email})
    else:
        return render(request, 'email_ui/partials/metadata_form.html', {
            'email': email,
            'metadata_form': form,
        }, status=400)


@login_required
def edit_metadata_form(request, pk):
    """Возвращает форму редактирования метаданных."""
    email = get_object_or_404(Email, pk=pk)
    form = EmailMetadataForm(instance=email)
    return render(request, 'email_ui/partials/metadata_form.html', {'email': email, 'metadata_form': form})


@login_required
def metadata_display(request, pk):
    """Возвращает отображение метаданных (для отмены редактирования)."""
    email = get_object_or_404(Email, pk=pk)
    return render(request, 'email_ui/partials/metadata_display.html', {'email': email})


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
    """Модальное окно для привязки к задачам."""
    email = get_object_or_404(Email, pk=pk)
    form = TaskSearchForm(request.GET or None)
    tasks = Task.objects.all()
    if form.is_valid() and form.cleaned_data.get('q'):
        tasks = tasks.filter(name__icontains=form.cleaned_data['q'])
    context = {
        'email': email,
        'tasks': tasks[:20],
        'search_form': form,
    }
    return render(request, 'email_ui/partials/task_selector.html', context)


@login_required
@require_http_methods(['POST'])
def attach_tasks(request, pk):
    """Привязка выбранных задач к письму."""
    email = get_object_or_404(Email, pk=pk)
    task_ids = sanitize_id_list(request.POST.getlist('tasks'))
    if task_ids:
        tasks = Task.objects.filter(id__in=task_ids)
        email.tasks.add(*tasks)
        messages.success(request, f'Письмо привязано к {len(tasks)} задачам')
    return HttpResponse(status=204)


@login_required
@require_http_methods(['POST'])
def detach_task(request, pk, task_id):
    """Отвязка задачи от письма."""
    email = get_object_or_404(Email, pk=pk)
    task = get_object_or_404(Task, pk=task_id)
    email.tasks.remove(task)
    return HttpResponse(status=204)


@login_required
@require_http_methods(['POST'])
def bulk_action(request):
    """Массовые операции над выбранными письмами."""
    action = request.POST.get('action')
    raw_ids = request.POST.getlist('selected_emails')
    email_ids = sanitize_id_list(raw_ids)
    if not email_ids:
        return HttpResponseBadRequest('Нет писем')

    emails = Email.objects.filter(id__in=email_ids)

    if action == 'move':
        folder = request.POST.get('folder')
        if folder in dict(Email.FOLDER_CHOICES):
            emails.update(folder=folder)
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

    folder = request.GET.get('folder', 'inbox')
    return redirect(reverse('email_ui:inbox', args=[folder]))


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
    """Возвращает количество непрочитанных писем (для боковой панели)."""
    count = Email.objects.filter(folder='inbox', is_read=False).count()
    return HttpResponse(str(count))


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


# ==================== Phase 2: Compose & Send ====================

@login_required
def compose_modal(request):
    """Модальное окно для создания нового письма."""
    form = ComposeEmailForm()
    return render(request, 'email_ui/partials/compose_modal.html', {
        'form': form,
        'mode': 'compose',
    })


@login_required
def reply_modal(request, pk, reply_type='reply'):
    """Модальное окно для ответа/пересылки."""
    email = get_object_or_404(Email, pk=pk)
    form = ComposeReplyForm(initial={'include_original': True})

    subject_map = {
        'reply': f'Re: {email.subject}',
        'reply_all': f'Re: {email.subject}',
        'forward': f'Fwd: {email.subject}',
    }

    context = {
        'form': form,
        'email': email,
        'mode': reply_type,
        'subject': subject_map.get(reply_type, email.subject),
        'to': email.sender if reply_type in ('reply', 'reply_all') else '',
        'cc': email.sender if reply_type == 'reply_all' else '',
    }
    return render(request, 'email_ui/partials/compose_modal.html', context)


@login_required
@require_http_methods(['POST'])
def send_email(request):
    """Отправка письма (AJAX)."""
    form = ComposeEmailForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, 'email_ui/partials/compose_modal.html', {
            'form': form, 'mode': 'compose',
        }, status=400)

    cd = form.cleaned_data
    use_outlook = cd.get('use_outlook', False)

    try:
        # Prepare attachments from uploaded files
        attachment_objs = []
        uploaded_files = request.FILES.getlist('attachment_files')
        for f in uploaded_files:
            # Save temporarily and create Attachment record
            att = Attachment.objects.create(
                email=None,
                file_path='',
                filename=f.name,
                size=f.size or 0,
                content_type=f.content_type or '',
            )
            attachment_objs.append(att)

        # Send
        sender = EmailSenderService(
            smtp_account=cd.get('smtp_account'),
            use_outlook=use_outlook,
        )

        to_list = [addr.strip() for addr in cd['to'].split(',') if addr.strip()]
        cc_list = [addr.strip() for addr in cd.get('cc', '').split(',') if addr.strip()]
        bcc_list = [addr.strip() for addr in cd.get('bcc', '').split(',') if addr.strip()]

        result = sender.send_via_smtp(
            to_emails=to_list,
            subject=cd['subject'],
            body_html=cd['body'],
            from_name=sender.smtp_account.from_name if sender.smtp_account else None,
            cc=cc_list if cc_list else None,
            bcc=bcc_list if bcc_list else None,
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
                is_read=True,
            )
            # Update attachments with email FK
            if attachment_objs:
                Attachment.objects.filter(id__in=[a.id for a in attachment_objs]).update(email=email_obj)

            messages.success(request, 'Письмо отправлено')
            return HttpResponse(status=204)

    except Exception as e:
        logger.exception(f'Ошибка отправки: {e}')
        return render(request, 'email_ui/partials/compose_modal.html', {
            'form': form, 'mode': 'compose', 'error': str(e),
        }, status=400)


@login_required
@require_http_methods(['POST'])
def reply_send(request, pk):
    """Отправка ответа на письмо."""
    email = get_object_or_404(Email, pk=pk)
    form = ComposeReplyForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest('Форма невалидна')

    cd = form.cleaned_data
    body = cd['body']
    if cd.get('include_original'):
        original_body = ''
        html_path = email.get_html_file_path()
        if html_path and os.path.exists(html_path):
            with open(html_path, 'r', encoding='utf-8') as f:
                original_body = f'<hr><blockquote>{f.read()}</blockquote>'
        body = body + original_body

    to_list = [email.sender] if email.sender else []
    cc_list = []
    if cd.get('reply_all') and email.cc:
        cc_list = [addr.strip() for addr in email.cc.split(',') if addr.strip()]

    try:
        sender = EmailSenderService()
        sender.send_via_smtp(
            to_emails=to_list,
            subject=f'Re: {email.subject}' if email.subject else 'Re:',
            body_html=body,
            cc=cc_list if cc_list else None,
            in_reply_to=email.message_id,
            references=email.references or email.message_id,
        )

        # Create reply record
        Email.objects.create(
            email_type='OUT',
            subject=f'Re: {email.subject}' if email.subject else 'Re:',
            sender=sender.smtp_account.from_email if sender.smtp_account else '',
            receiver=', '.join(to_list),
            folder='sent',
            sent_status='sent',
            sent_at=timezone.now(),
            is_read=True,
            in_reply_to=email.message_id,
            thread_id=email.thread_id,
        )

        messages.success(request, 'Ответ отправлен')
        return HttpResponse(status=204)
    except Exception as e:
        logger.exception(f'Ошибка отправки ответа: {e}')
        return HttpResponseBadRequest(str(e))


@login_required
@require_http_methods(['POST'])
def save_draft(request):
    """Сохранить черновик письма."""
    form = ComposeEmailForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest('Форма невалидна')

    cd = form.cleaned_data
    email_obj = Email.objects.create(
        email_type='OUT',
        subject=cd['subject'],
        sender='',
        receiver=cd['to'],
        cc=cd.get('cc', ''),
        bcc=cd.get('bcc', ''),
        folder='drafts',
        sent_status='draft',
    )
    messages.success(request, 'Черновик сохранён')
    return HttpResponse(status=204)


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
        'email': c.primary_email.email if c.primary_email else '',
        'company': c.company.name if c.company else '',
    } for c in contacts]
    return JsonResponse(data, safe=False)


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
        task_id=task_id,
        defaults={
            'link_type': link_type,
            'created_by': request.user,
        },
    )

    return JsonResponse({
        'success': True,
        'created': created,
        'link_id': link.id,
        'task_name': link.task.name,
    })


@login_required
@require_http_methods(['POST'])
def unlink_email_from_task(request, link_id):
    """Удалить связь письма с задачей."""
    link = get_object_or_404(EmailTaskLink, pk=link_id)
    link.delete()
    return HttpResponse(status=204)


@login_required
def create_task_from_email(request, pk):
    """Создать задачу из письма."""
    email = get_object_or_404(Email, pk=pk)
    if request.method == 'POST':
        from ProjectTDL.forms import TaskForm
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.owner = request.user
            task.save()
            EmailTaskLink.objects.create(
                email=email,
                task=task,
                link_type='created_from',
                created_by=request.user,
            )
            messages.success(request, f'Задача "{task.name}" создана из письма')
            return redirect(reverse('email_ui:inbox_default'))
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
    return render(request, 'email_ui/partials/email_thread.html', {
        'thread': thread,
        'active_email': email,
    })
