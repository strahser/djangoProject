# -*- coding: utf-8 -*-
"""Общая логика отправки писем (блок 3 рефакторинга).

Тройник send_email / reply_send / draft_send содержал три копии одного
и того же: парсинг to/cc/bcc, regex-валидация, создание OUT-записи,
сохранение вложений. Здесь — чистые переиспользуемые шаги; views решают
только mode-специфику (формы, фолбэки получателей, шаблоны ошибок).

Поведение сохранено 1:1, включая известные странности (помечены BUG).
"""
from __future__ import annotations

import logging
import os

from django.utils import timezone

from email_ui.utils import extract_all_email_addresses
from Emails.models import Attachment, Email
from Emails.ЕmailParser.EmailConfig import E_MAIL_DIRECTORY
from email_ui.services.email_sender import EmailSenderService

logger = logging.getLogger(__name__)


def parse_recipients(raw: str) -> list:
    """Адреса из строки: extract_all_email_addresses, иначе split(',').

    Тот же порядок, что был в send_email/draft_send: сначала умный парсер
    (уголки, ';'), фолбэк — грубая нарезка по запятой.
    """
    found = extract_all_email_addresses(raw or '')
    if found:
        return list(found)
    return [addr.strip() for addr in (raw or '').split(',') if addr.strip()]


def invalid_addresses(addresses) -> list:
    """Подмножество адресов, не прошедших _EMAIL_STANDALONE_RE."""
    from email_ui.utils import _EMAIL_STANDALONE_RE
    return [a for a in addresses if not _EMAIL_STANDALONE_RE.match(a)]


def build_sender(cleaned: dict) -> EmailSenderService:
    """EmailSenderService из cleaned_data формы (как в send/draft)."""
    return EmailSenderService(
        smtp_account=cleaned.get('smtp_account'),
        use_outlook=cleaned.get('use_outlook', False),
    )


def create_sent_email(*, sender, subject, to_list, cc_list,
                      bcc_list=None, in_reply_to=None,
                      thread_id=None) -> Email:
    """OUT-запись отправленного письма (единый формат для трёх views)."""
    return Email.objects.create(
        email_type='OUT',
        subject=subject,
        sender=sender.smtp_account.from_email if sender.smtp_account else '',
        receiver=', '.join(to_list),
        cc=', '.join(cc_list) if cc_list else None,
        bcc=', '.join(bcc_list) if bcc_list else None,
        folder='sent',
        sent_status='sent',
        sent_at=timezone.now(),
        email_stamp=timezone.now(),
        is_read=True,
        in_reply_to=in_reply_to,
        thread_id=thread_id,
    )


def persist_uploaded_files(email_obj, uploaded_files) -> None:
    """Новые загруженные файлы: запись Attachment + копия на диск.

    Без email.link файлы складываются в E_MAIL_DIRECTORY/sent/<id> (раньше
    молча терялись с file_path == ''). Путь фиксируется в link записи.
    Ошибки одного файла только логируются, остальные сохраняются.
    """
    for f in uploaded_files or []:
        try:
            att = Attachment(
                email=email_obj,
                filename=f.name,
                size=f.size or 0,
                content_type=f.content_type or '',
                file_path='',
            )
            target_dir = email_obj.link
            if not target_dir:
                target_dir = os.path.join(
                    E_MAIL_DIRECTORY, 'sent', str(email_obj.pk))
                os.makedirs(target_dir, exist_ok=True)
                email_obj.link = target_dir
                email_obj.save(update_fields=['link'])
            os.makedirs(target_dir, exist_ok=True)
            file_path = os.path.join(target_dir, f.name)
            with open(file_path, 'wb+') as dest:
                for chunk in f.chunks():
                    dest.write(chunk)
            att.file_path = file_path
            att.save()
        except Exception as e:
            logger.warning(f'Ошибка сохранения вложения {f.name}: {e}')


def copy_attachment_rows(new_email, attachments, excluded_ids) -> None:
    """Копии строк Attachment (пересылка/черновик): только записи, без файлов."""
    for att in attachments or []:
        if att.pk in (excluded_ids or set()):
            continue
        Attachment.objects.create(
            email=new_email,
            filename=att.filename,
            file_path=att.file_path,
            size=att.size,
            content_type=att.content_type,
        )


def parse_excluded_ids(post) -> set:
    """IDs вложений, снятых чекбоксом exclude_attachments (reply/draft)."""
    from email_ui.utils import sanitize_id
    excluded = set()
    for val in post.getlist('exclude_attachments'):
        try:
            excluded.add(sanitize_id(val))
        except (ValueError, TypeError):
            continue
    return excluded
