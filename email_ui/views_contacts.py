# -*- coding: utf-8 -*-
"""P2: справочные CRUD-вьюхи email_ui — контакты, группы, теги.

Вынесено из views.py (2055 строк) 1:1: поведение, шаблоны, коды ответов
не менялись, url-имена в email_ui/urls.py те же (шаблоны не тронуты).
_save_modal_form переехал в services/modal_forms.py.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from Emails.models import Email
from .forms import ContactEmailForm, ContactForm, ContactGroupForm, EmailTagForm
from .models import Contact, ContactEmail, ContactGroup, EmailEmailTag, EmailTag
from .services.modal_forms import save_modal_form
from .services.navigation import _safe_next
from .utils import sanitize_id, sanitize_id_list


# ==================== Contacts ====================


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
    return save_modal_form(
        request, form, template='email_ui/partials/contact_modal.html',
        mode='edit', message='Контакт обновлён',
        extra={'contact': contact})


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
    contacts = list(Contact.objects.filter(
        Q(name__icontains=query) | Q(emails__email__icontains=query)
    ).distinct().select_related('company').prefetch_related('emails')[:10])
    if query and any(ord(c) > 127 for c in query):
        # SQLite LIKE регистронезависим только для ASCII: кириллицу
        # добираем casefold-сравнением в Python (кап 500 кандидатов).
        qfold = query.casefold()
        seen = {c.pk for c in contacts}
        extra = Contact.objects.exclude(pk__in=seen).select_related(
            'company').prefetch_related('emails')[:500]
        for c in extra:
            cached = list(c.emails.all())
            if qfold in c.name.casefold() or any(
                    qfold in e.email.casefold() for e in cached):
                contacts.append(c)
                if len(contacts) >= 10:
                    break
    data = []
    for c in contacts:
        # Блок 10: адреса из prefetch-кэша, без запросов на строку.
        cached = list(c.emails.all())
        primary = next((e for e in cached if e.is_primary), None)
        data.append({
            'id': c.id,
            'name': c.name,
            'email': primary.email if primary else (cached[0].email if cached else ''),
            'company': c.company.name if c.company else '',
        })
    return JsonResponse(data, safe=False)


# ==================== Contact Groups ====================


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
    return save_modal_form(
        request, form, template='email_ui/partials/group_modal.html',
        mode='create',
        message=lambda group: f'Группа "{group.name}" создана')


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
    return save_modal_form(
        request, form, template='email_ui/partials/group_modal.html',
        mode='edit', message='Группа обновлена',
        extra={'group': group})


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


# ==================== Tags ====================


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
    return save_modal_form(
        request, form, template='email_ui/partials/tag_modal.html',
        mode='create',
        message=lambda tag: f'Тег "{tag.name}" создан')


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
    try:
        email_id = sanitize_id(request.POST.get('email_id'))
    except (ValueError, TypeError):
        return HttpResponseBadRequest('Некорректный ID письма')
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

    # Блок 10: пачка вместо get_or_create в цикле (гонки + N запросов).
    existing = set(EmailEmailTag.objects.filter(
        email_id__in=email_ids, tag=tag).values_list('email_id', flat=True))
    EmailEmailTag.objects.bulk_create(
        [EmailEmailTag(email_id=eid, tag=tag, added_by=request.user)
         for eid in email_ids if eid not in existing],
        ignore_conflicts=True,
    )

    messages.success(request, f'Тег "{tag.name}" назначен {emails.count()} письмам')
    return HttpResponse(status=204)
