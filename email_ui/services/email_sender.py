import logging
import os
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from typing import List, Optional, Union

from django.conf import settings
from django.utils import timezone

from Emails.models import Email, Attachment
from email_ui.models import SMTPAccount, EmailTemplate

logger = logging.getLogger(__name__)


class EmailSenderService:
    """Унифицированный сервис отправки писем через SMTP или Outlook COM."""

    def __init__(self, smtp_account: Optional[SMTPAccount] = None, use_outlook: bool = False):
        self.use_outlook = use_outlook
        self.smtp_account = smtp_account or SMTPAccount.objects.filter(
            is_default=True, is_active=True
        ).first()
        self._outlook = None

    def send_via_smtp(
        self,
        to_emails: List[str],
        subject: str,
        body_html: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[Union[Attachment, object]]] = None,
        message_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> bool:
        """Отправка письма через SMTP."""
        account = self.smtp_account
        if not account:
            raise ValueError('Нет активного SMTP аккаунта. Настройте SMTPAccount в админке.')

        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = formataddr((
            from_name or account.from_name or '',
            from_email or account.from_email,
        ))
        msg['To'] = ', '.join(to_emails)
        msg['Date'] = formatdate(localtime=True)

        if cc:
            msg['Cc'] = ', '.join(cc)
        if reply_to:
            msg['Reply-To'] = reply_to
        if message_id:
            msg['Message-ID'] = message_id
        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to
        if references:
            msg['References'] = references

        body_part = MIMEMultipart('alternative')
        body_part.attach(MIMEText(body_html, 'html', 'utf-8'))
        msg.attach(body_part)

        if attachments:
            for att in attachments:
                self._attach_file(msg, att)

        all_recipients = list(to_emails) + (cc or []) + (bcc or [])

        try:
            if account.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(account.host, account.port, context=context) as server:
                    server.login(account.username, account.password)
                    server.sendmail(account.from_email, all_recipients, msg.as_string())
            else:
                with smtplib.SMTP(account.host, account.port) as server:
                    if account.use_tls:
                        server.starttls(context=ssl.create_default_context())
                    server.login(account.username, account.password)
                    server.sendmail(account.from_email, all_recipients, msg.as_string())

            logger.info(f'Письмо отправлено: "{subject}" -> {to_emails}')

            try:
                self._save_copy_to_imap_sent(msg)
            except Exception:
                pass

            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f'Ошибка аутентификации SMTP ({account.host}): {e}')
            raise
        except smtplib.SMTPException as e:
            logger.error(f'Ошибка SMTP ({account.host}:{account.port}): {e}')
            raise
        except OSError as e:
            logger.error(f'Сетевая ошибка при отправке через {account.host}:{account.port}: {e}')
            raise

    @staticmethod
    def _save_copy_to_imap_sent(msg: MIMEMultipart) -> None:
        """Сохраняет копию отправленного письма в IMAP-папку «Отправленные»."""
        from imap_tools import MailBox

        host = getattr(settings, 'YA_HOST', '')
        user = getattr(settings, 'YA_USER', '')
        password = getattr(settings, 'YA_PASSWORD', '')
        if not host or not user or not password:
            logger.info('IMAP credentials not configured, skipping save to Sent folder')
            return

        try:
            with MailBox(host, getattr(settings, 'YA_PORT', 993)) as mailbox:
                mailbox.login(user, password)
                mailbox.append(
                    msg.as_bytes(),
                    folder='Отправленные',
                    flag_set=['\\Seen'],
                )
            logger.info('Копия письма сохранена в IMAP Отправленные')
        except Exception as e:
            logger.warning(f'Не удалось сохранить копию в IMAP Отправленные: {e}')

    @staticmethod
    def _attach_file(msg: MIMEMultipart, att) -> None:
        """Прикрепляет файл к сообщению. Поддерживает Attachment и UploadedFile."""
        try:
            if hasattr(att, 'read') and hasattr(att, 'name'):
                data = att.read()
                fname = att.name
                part = MIMEApplication(data, Name=fname)
                part['Content-Disposition'] = f'attachment; filename="{fname}"'
                msg.attach(part)
                return

            if hasattr(att, 'file_path') and att.file_path and os.path.exists(att.file_path):
                with open(att.file_path, 'rb') as f:
                    part = MIMEApplication(f.read(), Name=att.filename)
                part['Content-Disposition'] = f'attachment; filename="{att.filename}"'
                if hasattr(att, 'content_id') and att.content_id:
                    part['Content-ID'] = f'<{att.content_id}>'
                msg.attach(part)
                return

            fname = getattr(att, 'filename', getattr(att, 'name', 'unknown'))
            logger.warning(f'Вложение не найдено: {fname}')

        except FileNotFoundError:
            fname = getattr(att, 'filename', getattr(att, 'name', 'unknown'))
            logger.warning(f'Файл вложения не найден: {fname}')
        except Exception as e:
            fname = getattr(att, 'filename', getattr(att, 'name', 'unknown'))
            logger.warning(f'Ошибка прикрепления {fname}: {e}')

    def _get_outlook(self):
        if self._outlook is None:
            import win32com.client
            self._outlook = win32com.client.Dispatch('Outlook.Application')
        return self._outlook

    def send_via_outlook(
        self,
        to_emails: List[str],
        subject: str,
        body_html: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Attachment]] = None,
        save_sent: bool = True,
    ) -> bool:
        """Отправка через Outlook COM (только Windows)."""
        outlook = self._get_outlook()
        mail = outlook.CreateItem(0)
        mail.To = '; '.join(to_emails)
        if cc:
            mail.CC = '; '.join(cc)
        if bcc:
            mail.BCC = '; '.join(bcc)
        mail.Subject = subject
        mail.HTMLBody = body_html

        if attachments:
            for att in attachments:
                try:
                    if hasattr(att, 'file_path') and os.path.exists(att.file_path):
                        mail.Attachments.Add(att.file_path)
                except Exception as e:
                    logger.warning(f'Не удалось прикрепить {getattr(att, "filename", "?")}: {e}')

        if save_sent:
            mail.Save()
        else:
            mail.Send()

        logger.info(f'Outlook: письмо создано "{subject}"')
        return True

    def send_email(self, email_obj: Email, attachments: Optional[List[Attachment]] = None) -> bool:
        """Отправляет объект Email."""
        to_list = [email_obj.receiver] if email_obj.receiver else []
        cc_list = email_obj.cc.split(',') if email_obj.cc else None
        bcc_list = email_obj.bcc.split(',') if email_obj.bcc else None

        if self.use_outlook:
            return self.send_via_outlook(
                to_emails=to_list,
                subject=email_obj.subject or '',
                body_html=self._get_html_body(email_obj),
                cc=cc_list,
                bcc=bcc_list,
                attachments=attachments or list(email_obj.attachments.all()),
            )
        return self.send_via_smtp(
            to_emails=to_list,
            subject=email_obj.subject or '',
            body_html=self._get_html_body(email_obj),
            from_email=self.smtp_account.from_email if self.smtp_account else None,
            cc=cc_list,
            bcc=bcc_list,
            reply_to=email_obj.reply_to,
            message_id=email_obj.message_id,
            in_reply_to=email_obj.in_reply_to,
            references=email_obj.references,
            attachments=attachments or list(email_obj.attachments.all()),
        )

    @staticmethod
    def _get_html_body(email_obj: Email) -> str:
        html_path = email_obj.get_html_file_path()
        if html_path:
            try:
                with open(html_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except (FileNotFoundError, OSError):
                pass
        return f'<p>{email_obj.subject or ""}</p>'

    def send_from_template(
        self,
        template: EmailTemplate,
        context_data: dict,
        to_emails: List[str],
        attachments: Optional[List[Attachment]] = None,
        **kwargs,
    ) -> bool:
        from django.template import Template, Context
        subject = Template(template.subject_template).render(Context(context_data))
        body_html = Template(template.body_template).render(Context(context_data))
        return self.send_via_smtp(
            to_emails=to_emails, subject=subject, body_html=body_html,
            attachments=attachments, **kwargs,
        )

    def send_bulk(self, email_ids: List[int], delay_seconds: int = 2) -> dict:
        """Массовая отправка с задержкой."""
        import time
        results = {'sent': 0, 'failed': 0, 'errors': []}
        emails = Email.objects.filter(id__in=email_ids)
        for email_obj in emails:
            try:
                self.send_email(email_obj)
                email_obj.sent_status = 'sent'
                email_obj.sent_at = timezone.now()
                email_obj.save(update_fields=['sent_status', 'sent_at'])
                results['sent'] += 1
            except Exception as e:
                logger.exception(f'Ошибка отправки письма {email_obj.id}: {e}')
                email_obj.sent_status = 'failed'
                email_obj.error_message = str(e)
                email_obj.save(update_fields=['sent_status', 'error_message'])
                results['failed'] += 1
                results['errors'].append({'email_id': email_obj.id, 'error': str(e)})
            if delay_seconds:
                time.sleep(delay_seconds)
        return results
