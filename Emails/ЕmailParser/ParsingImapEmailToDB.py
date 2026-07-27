import os
from typing import List, Optional

from loguru import logger
from imap_tools import MailBox

from Emails.models import Email, Attachment
from Emails.ЕmailParser.EmailImapMessage import EmailImapMessage
from Emails.ЕmailParser.DbEmailImapMessageSerializer import DbEmailImapMessageSerializer
from Emails.ЕmailParser.EmailConfig import YA_HOST, YA_USER, YA_PASSWORD
from Emails.ЕmailParser.sanitize import sanitize_filename


class ParsingImapEmailToDB:
    """Парсер IMAP-писем с сохранением в БД и на диск."""

    EXCLUDE_PATTERNS = [
        'Image.*.png',
        'custom_table_view.html',
        '*.html',
        'ecblank.gif',
    ]

    def __init__(self, root_folder_path: str):
        self.root_folder_path = root_folder_path
        self.create_action_list: List[str] = []
        self.skip_action_list: List[str] = []
        self.error_list: List[str] = []

    @staticmethod
    def _create_folder(directory: str) -> None:
        os.makedirs(directory, exist_ok=True)

    def _get_existing_uids(self) -> set:
        """Получает множество существующих UID из БД (оптимизация: set вместо list)."""
        return set(Email.objects.values_list('uid', flat=True))

    def save_attachment(self, attach, folder_path: str) -> Optional[str]:
        """Сохраняет вложение на диск и возвращает полный путь к файлу."""
        safe_filename = sanitize_filename(attach.filename)
        full_path = os.path.join(folder_path, safe_filename)

        try:
            with open(full_path, 'wb') as f:
                f.write(attach.payload)
            logger.debug(f"Сохранено вложение: {safe_filename}")
            return full_path
        except OSError as e:
            logger.error(f"Ошибка сохранения {attach.filename}: {e}")
            try:
                ascii_name = ''.join(
                    c if ord(c) < 128 else '_' for c in attach.filename
                )
                full_path = os.path.join(folder_path, ascii_name)
                with open(full_path, 'wb') as f:
                    f.write(attach.payload)
                logger.info(f"Сохранено после ascii-очистки: {ascii_name}")
                return full_path
            except OSError as e2:
                logger.error(f"Не удалось сохранить даже после ascii-очистки: {e2}")
                return None

    def _is_skippable_attachment(self, filename: str) -> bool:
        """Проверяет, нужно ли исключать вложение из БД."""
        for pattern in self.EXCLUDE_PATTERNS:
            if pattern.startswith('*') and pattern.endswith('*'):
                if pattern[1:-1] in filename:
                    return True
            elif pattern.startswith('*'):
                if filename.endswith(pattern[1:]):
                    return True
            elif pattern.endswith('*'):
                if filename.startswith(pattern[:-1]):
                    return True
            elif pattern == filename:
                return True
        return False

    def _process_attachments(self, msg, email_obj, folder_path: str) -> None:
        """Обрабатывает все вложения письма."""
        for attach in msg.attachments:
            try:
                saved_path = self.save_attachment(attach, folder_path)
            except Exception:
                logger.exception(
                    f"Не удалось сохранить вложение {attach.filename} "
                    f"для письма {msg.uid}"
                )
                continue

            if saved_path and not self._is_skippable_attachment(attach.filename):
                try:
                    Attachment.objects.get_or_create(
                        email=email_obj,
                        filename=attach.filename,
                        defaults={
                            'file_path': saved_path,
                            'size': attach.size or 0,
                            'content_type': attach.content_type or '',
                        },
                    )
                except Exception as e:
                    logger.error(f"Ошибка создания записи вложения {attach.filename}: {e}")

    def main(self, email_type: str, folder: str, limit: Optional[int] = None) -> None:
        """Основной метод: подключается к IMAP и обрабатывает письма."""
        existing_uids = self._get_existing_uids()

        try:
            with MailBox(YA_HOST).login(YA_USER, YA_PASSWORD, initial_folder=folder) as mailbox:
                for msg in mailbox.fetch(reverse=True, limit=limit):
                    if msg.uid in existing_uids:
                        self.skip_action_list.append(msg.uid)
                        continue

                    self.create_action_list.append(msg.uid)

                    try:
                        message = EmailImapMessage(self.root_folder_path, msg)
                        self._create_folder(message.folder_path_name)

                        message.save_e_mail_to_html()

                        serializer = DbEmailImapMessageSerializer(
                            email_type, message.folder_path_name, msg
                        )
                        email_obj = serializer.create_record()

                        self._process_attachments(msg, email_obj, message.folder_path_name)

                    except Exception as e:
                        logger.exception(f"Ошибка обработки письма {msg.uid}: {e}")
                        self.error_list.append(msg.uid)

        except Exception as e:
            logger.exception(f"Ошибка подключения к IMAP ({folder}): {e}")
            self.error_list.append(f'IMAP connection: {e}')
