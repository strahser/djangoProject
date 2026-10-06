"""Блок 27 (B1): шаги compose-потока (вынесено из views.py 1:1).

send_email / reply_send / draft_send / save_draft делили одни и те же
подшаги: активные контакты, пикер-контекст, fallback получателей ответа,
Re:/Fwd:-тема, сбор вложений, записи вложений черновика, каталог черновика.
Views оставляют себе формы, шаблоны ошибок и сам вызов SMTP.
"""
from email_ui.models import Contact


def active_contacts():
    """Активные контакты с префетчем почт (единый queryset пикера)."""
    return Contact.objects.filter(is_active=True).prefetch_related('emails')


def contacts_picker_json(contacts):
    """Единый источник данных пикера контактов: список [{n: имя, e: email}].

    Возвращает Python-список — сериализует шаблонный фильтр json_script.
    """
    from email_ui.utils import canonical_email
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


def groups_picker_json(groups=None):
    """Группы для пикера: [{n: название, e: [твёрдые почты плоско]}]."""
    from email_ui.models import ContactGroup
    if groups is None:
        groups = ContactGroup.objects.filter(is_active=True).prefetch_related(
            'contacts__emails', 'subgroups',
        )
    return [{'n': g.name, 'e': g.all_emails()} for g in groups]


def picker_context(contacts):
    """Кусок render-контекста с пикеров (контакты + группы)."""
    return {
        'contacts': contacts,
        'contacts_json': contacts_picker_json(contacts),
        'groups_json': groups_picker_json(),
    }


def current_user_email(request):
    """Email текущего пользователя строчными ('' если нет)."""
    user = getattr(request, 'user', None)
    return (user.email or '').lower() if user and hasattr(user, 'email') else ''


def reply_all_recipients(email, user_email=''):
    """To/Cc для «Ответить всем» по исходному письму.

    Единая логика для префилла модалки и fallback отправки:
    To — явный адрес отправителя; Cc — явные адреса из To/Cc
    минус отправитель, свои адреса (пользователь, YA_USER,
    аккаунт письма, все активные SMTP). Возвращает (to, cc, missing),
    где missing — entries без явного email (не подменяются контактами).
    """
    from django.conf import settings

    from email_ui.models import SMTPAccount
    from email_ui.utils import extract_email_address, resolve_sender_to_email
    sender_email = resolve_sender_to_email(email.sender or '')
    excluded = set()
    if sender_email:
        excluded.add(sender_email.lower())
    if user_email:
        excluded.add(user_email.lower())
    ya_user = getattr(settings, 'YA_USER', '') or ''
    if ya_user:
        excluded.add(ya_user.lower())
    if email.smtp_account and email.smtp_account.from_email:
        excluded.add(email.smtp_account.from_email.lower())
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


def resolve_reply_recipients(email, to_raw, cc_raw, mode, user_email=''):
    """Получатели ответа/пересылки с фолбэками и regex-чисткой.

    Возвращает (to_list, cc_list); пустота to_list — повод для 400 во view.
    """
    from email_ui.utils import (
        _EMAIL_STANDALONE_RE,
        extract_all_email_addresses,
        resolve_sender_to_email,
    )
    if not to_raw and mode in ('reply', 'reply_all'):
        # Адрес извлекается ТОЛЬКО явно из поля From. Нечёткий поиск запрещён.
        to_raw = resolve_sender_to_email(email.sender or '')
    to_list = extract_all_email_addresses(to_raw or '')
    if not cc_raw and mode == 'reply_all':
        # Тот же расчёт, что префилл модалки: с исключениями себя/отправителя/ящиков.
        _, cc_raw, _ = reply_all_recipients(email, user_email)
    cc_list = extract_all_email_addresses(cc_raw or '')
    # БЕЗОПАСНОСТЬ: только действительные адреса (защита от подстановки).
    to_list = [a for a in to_list if _EMAIL_STANDALONE_RE.match(a)]
    cc_list = [a for a in cc_list if _EMAIL_STANDALONE_RE.match(a)]
    return to_list, cc_list


def resolve_subject(email_subject, subject, mode):
    """Тема ответа/пересылки: введённая или Re:/Fwd:-фолбэк."""
    if subject:
        return subject
    if mode == 'forward':
        return f'Fwd: {email_subject}' if email_subject else 'Fwd:'
    return f'Re: {email_subject}' if email_subject else 'Re:'


def collect_reply_attachments(email, include_attachments, excluded_ids,
                              uploaded_files):
    """Вложения к отправке: записи оригинала (минус снятые) + загруженные."""
    attachment_objs = []
    if include_attachments:
        for att in email.attachments.all():
            if att.pk in excluded_ids:
                continue
            attachment_objs.append(att)
    for f in uploaded_files or []:
        attachment_objs.append(f)
    return attachment_objs


def record_draft_attachments(email_obj, attachment_objs):
    """Записи вложений отправленного черновика: копии строк + новые файлы."""
    from Emails.models import Attachment

    from email_ui.services import compose_service as compose
    for att in attachment_objs or []:
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
            compose.persist_uploaded_files(email_obj, [att])


def prepare_draft_dir(subject_val, body_val):
    """Каталог черновика ts_тема + HTML тела. Возвращает путь каталога."""
    import os
    from datetime import datetime

    from django.conf import settings
    # Создаём директорию черновиков
    draft_dir = os.path.join(settings.DRAFT_DIRECTORY)
    os.makedirs(draft_dir, exist_ok=True)

    # Создаём уникальную поддиректорию для письма
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    subject_clean = subject_val[:50] if subject_val else 'no_subject'
    safe_subject = ''.join(
        c if c.isalnum() or c in ' -_.,()' else '_' for c in subject_clean
    ).strip()
    email_dir = os.path.join(draft_dir, f'{ts}_{safe_subject}')
    os.makedirs(email_dir, exist_ok=True)

    # Сохраняем HTML тело
    if body_val:
        body_path = os.path.join(email_dir, f'{safe_subject}.html')
        with open(body_path, 'w', encoding='utf-8') as f:
            f.write(body_val)
    return email_dir
