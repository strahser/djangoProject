import subprocess
from sys import platform

from django.contrib.admin.utils import flatten
from django.urls import reverse
from loguru import logger  # <-- замена стандартному logging
import os
import mimetypes
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseBadRequest, FileResponse, Http404, JsonResponse
from django.db.models import Q
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages

from Emails.models import Email, Attachment, InfoChoices, EmailType
from Emails.ЕmailParser.EmailConfig import E_MAIL_DIRECTORY
from Emails.ЕmailParser.ParsingImapEmailToDB import ParsingImapEmailToDB
from ProjectContract.models import Contractor
from ProjectTDL.models import Task
from StaticData.models import ProjectSite, BuildingType, Category
from .forms import EmailFilterForm, EmailMetadataForm, TaskSearchForm
from .utils import clean_email_html
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from Emails.models import Email
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

    # Данные для преобразования ID в названия в шаблоне и JS
    filter_data = {
        'project_site': {str(obj.id): obj.name for obj in ProjectSite.objects.all()},
        'contractor': {str(obj.id): obj.name for obj in Contractor.objects.all()},
        'building_type': {str(obj.id): obj.name for obj in BuildingType.objects.all()},
        'category': {str(obj.id): obj.name for obj in Category.objects.all()},
        'info': dict(InfoChoices.choices),
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
        'filter_data': filter_data,
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
    else:
        messages.error(request, 'Некорректная папка')
    return HttpResponse(status=204)


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
    task_ids = request.POST.getlist('tasks')
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
    email_ids = request.POST.getlist('selected_emails')
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
    return email_list_partial(request)


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
