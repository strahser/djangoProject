import logging
import os
import shutil
from datetime import datetime
from email import message_from_string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formatdate, formataddr
from typing import List, Optional

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest

from Emails.models import Email, Attachment, EmailType
from Emails.ЕmailParser.sanitize import clean

logger = logging.getLogger(__name__)


class EmailExportService:
    """
    Service for exporting/copying emails to disk in various formats.
    Extends the existing copy_e_mail admin action.
    """

    @staticmethod
    def export_as_eml(email: Email, output_path: str) -> str:
        """Export email as .eml (RFC 822 format)."""
        msg = MIMEMultipart('mixed')
        msg['Subject'] = email.subject or ''
        msg['From'] = email.sender or ''
        msg['To'] = email.receiver or ''
        msg['Date'] = email.email_stamp.strftime('%a, %d %b %Y %H:%M:%S %z') if email.email_stamp else formatdate(localtime=True)
        msg['Message-ID'] = email.message_id or ''

        body_html = ''
        html_path = email.get_html_file_path()
        if html_path and os.path.exists(html_path):
            with open(html_path, 'r', encoding='utf-8') as f:
                body_html = f.read()

        if body_html:
            msg.attach(MIMEText(body_html, 'html', 'utf-8'))

        for att in email.attachments.all():
            if os.path.exists(att.file_path):
                with open(att.file_path, 'rb') as f:
                    part = MIMEApplication(f.read(), Name=att.filename)
                part['Content-Disposition'] = f'attachment; filename="{att.filename}"'
                msg.attach(part)

        filename = os.path.join(output_path, f'{email.id}_{clean(email.subject or "no_subject")}.eml')
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(msg.as_string())

        return filename

    @staticmethod
    def export_as_html(email: Email, output_path: str) -> str:
        """Export email as standalone HTML file."""
        html_path = email.get_html_file_path()
        if html_path and os.path.exists(html_path):
            filename = os.path.join(output_path, f'{email.id}_{clean(email.subject or "no_subject")}.html')
            shutil.copy2(html_path, filename)
            return filename
        return ''

    @staticmethod
    def export_as_mbox(emails: List[Email], output_path: str) -> str:
        """Export multiple emails to mbox format."""
        from email import message_from_string

        filename = os.path.join(output_path, f'export_{datetime.now():%Y%m%d_%H%M%S}.mbox')
        with open(filename, 'w', encoding='utf-8') as mbox_file:
            for email in emails:
                eml_path = EmailExportService.export_as_eml(email, output_path)
                if eml_path:
                    with open(eml_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    mbox_file.write(f'From {email.sender or "unknown"} {email.email_stamp or ""}\n')
                    mbox_file.write(content)
                    mbox_file.write('\n\n')
        return filename

    @staticmethod
    def copy_to_directory(
        email: Email,
        target_dir: str,
        copy_attachments: bool = True,
        organize_by: str = 'date',
    ) -> str:
        """
        Copy email files to a structured directory (like existing copy_e_mail action).
        organize_by: date | sender | project | thread
        """
        if organize_by == 'date' and email.email_stamp:
            folder = os.path.join(target_dir, email.email_stamp.strftime('%Y'), email.email_stamp.strftime('%Y_%m_%d'))
        elif organize_by == 'sender':
            folder = os.path.join(target_dir, clean(email.sender or 'unknown'))
        elif organize_by == 'project' and email.project_site:
            folder = os.path.join(target_dir, clean(email.project_site.name))
        else:
            folder = target_dir

        email_folder_name = f'{email.id}_{clean(email.subject or "no_subject")}'
        email_folder = os.path.join(folder, email_folder_name)
        os.makedirs(email_folder, exist_ok=True)

        # Copy HTML body
        html_path = email.get_html_file_path()
        if html_path and os.path.exists(html_path):
            shutil.copy2(html_path, os.path.join(email_folder, 'email.html'))

        # Copy attachments
        if copy_attachments:
            for att in email.attachments.all():
                if os.path.exists(att.file_path):
                    shutil.copy2(att.file_path, os.path.join(email_folder, att.filename))

        # Save metadata
        metadata_path = os.path.join(email_folder, 'metadata.txt')
        with open(metadata_path, 'w', encoding='utf-8') as f:
            f.write(f'Subject: {email.subject}\n')
            f.write(f'From: {email.sender}\n')
            f.write(f'To: {email.receiver}\n')
            f.write(f'Date: {email.email_stamp}\n')
            f.write(f'Project: {email.project_site}\n')
            f.write(f'Contractor: {email.contractor}\n')

        return email_folder

    @staticmethod
    def export_selected(
        email_ids: List[int],
        export_path: str,
        format: str = 'eml',
        include_attachments: bool = True,
        organize_by: str = 'date',
    ) -> dict:
        """
        Export multiple emails.
        Formats: 'eml', 'html', 'mbox', 'copy' (structured directory)
        """
        results = {'exported': 0, 'failed': 0, 'files': []}
        emails = Email.objects.filter(id__in=email_ids)

        for email in emails:
            try:
                os.makedirs(export_path, exist_ok=True)

                if format == 'eml':
                    filepath = EmailExportService.export_as_eml(email, export_path)
                elif format == 'html':
                    filepath = EmailExportService.export_as_html(email, export_path)
                elif format == 'copy':
                    filepath = EmailExportService.copy_to_directory(email, export_path, include_attachments, organize_by)
                else:
                    raise ValueError(f'Unknown format: {format}')

                if filepath:
                    results['files'].append(filepath)
                    results['exported'] += 1
            except Exception as e:
                logger.exception(f'Export failed for email {email.id}: {e}')
                results['failed'] += 1

        return results
