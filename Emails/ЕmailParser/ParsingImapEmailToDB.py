import os
from loguru import logger
from imap_tools import MailBox

from Emails.models import Email, Attachment
from Emails.ЕmailParser.EmailImapMessage import EmailImapMessage
from Emails.ЕmailParser.DbEmailImapMessageSerializer import DbEmailImapMessageSerializer
from Emails.ЕmailParser.EmailConfig import YA_HOST, YA_USER, YA_PASSWORD
from Emails.ЕmailParser.sanitize import sanitize_filename   # новая функция очистки


UID_LIST = list(Email.objects.values_list('uid', flat=True).all())

class ParsingImapEmailToDB:
    def __init__(self, root_folder_path):
        self.root_folder_path = root_folder_path
        self.create_action_list = []
        self.skip_action_list = []

    @staticmethod
    def _create_folder(_directory):
        os.makedirs(_directory, exist_ok=True)


    def save_attachment(self, attach, folder_path):
        """Сохраняет вложение на диск и возвращает полный путь к файлу."""
        safe_filename = sanitize_filename(attach.filename)
        full_path = os.path.join(folder_path, safe_filename)
        try:
            with open(full_path, 'wb') as f:
                f.write(attach.payload)
            logger.info(f"Сохранено вложение: {safe_filename} (исходное: {attach.filename})")
        except Exception as e:
            logger.error(f"Ошибка сохранения вложения {attach.filename} (очищенное имя: {safe_filename}): {e}")
            # Пробуем ещё более жёсткую очистку (только ASCII)
            try:
                ascii_name = ''.join(c if ord(c) < 128 else '_' for c in attach.filename)
                full_path = os.path.join(folder_path, ascii_name)
                with open(full_path, 'wb') as f:
                    f.write(attach.payload)
                logger.info(f"Сохранено вложение после ascii-очистки: {ascii_name}")
                # Обновляем путь для возврата
                full_path = os.path.join(folder_path, ascii_name)
            except Exception as e2:
                logger.error(f"Не удалось сохранить вложение даже после ascii-очистки: {e2}")
                raise   # пробрасываем исключение дальше, чтобы не создавать запись в БД без файла
        return full_path


    def _is_skippable_attachment(self, filename):
        """Проверяет, нужно ли исключать вложение из базы данных (служебные файлы)."""
        exclude_patterns = ['Image.*.png', 'custom_table_view.html']
        for pattern in exclude_patterns:
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

    def main(self, email_type, folder, limit=None):
        with MailBox(YA_HOST).login(YA_USER, YA_PASSWORD, initial_folder=folder) as mailbox:
            for msg in mailbox.fetch(reverse=True, limit=limit):
                if msg.uid in UID_LIST:
                    self.skip_action_list.append(msg.uid)
                    continue

                self.create_action_list.append(msg.uid)

                try:
                    # 1. Создаём объект сообщения и папку
                    message = EmailImapMessage(self.root_folder_path, msg)
                    self._create_folder(message.folder_path_name)

                    # 2. Сохраняем HTML письма
                    message.save_e_mail_to_html()

                    # 3. Создаём запись Email (получаем объект)
                    serializer = DbEmailImapMessageSerializer(email_type, message.folder_path_name, msg)
                    email_obj = serializer.create_record()

                    # 4. Сохраняем вложения и создаём связанные записи Attachment
                    for attach in msg.attachments:
                        try:
                            saved_path = self.save_attachment(attach, message.folder_path_name)
                        except Exception as e:
                            logger.exception(f"Не удалось сохранить файл вложения {attach.filename} для письма {msg.uid}, пропускаем")
                            continue   # пропускаем это вложение, идём дальше

                        if not self._is_skippable_attachment(attach.filename):
                            try:
                                Attachment.objects.create(
                                    email=email_obj,
                                    file_path=saved_path,
                                    filename=attach.filename,
                                    size=attach.size,
                                    content_type=attach.content_type
                                )
                                logger.debug(f"Создана запись вложения для {attach.filename}")
                            except Exception as e:
                                logger.error(f"Ошибка создания записи вложения {attach.filename}: {e}")
                except Exception as e:
                    logger.exception(f"Ошибка обработки письма {msg.uid}: {e}")