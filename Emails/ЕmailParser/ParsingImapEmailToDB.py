import imaplib
import os
import time
from typing import List, Optional

from loguru import logger
from imap_tools import AND, MailBox

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

    def _get_existing_uids(self, folder_db: str = None) -> set:
        """Множество UID, уже загруженных в БД.

        UID уникален только внутри одной IMAP-папки, поэтому для папки
        запрашиваем только её записи (folder='inbox'/'sent'). Глобальный
        запрос по всем папкам пропускал письма: UID из sent совпадал
        с уже загруженным UID из inbox и письмо молча не импортировалось.
        """
        qs = Email.objects.exclude(uid__isnull=True).exclude(uid='')
        if folder_db:
            qs = qs.filter(folder=folder_db)
        return set(qs.values_list('uid', flat=True))

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
                            'content_id': getattr(attach, 'content_id', '') or '',
                            'is_inline': bool(getattr(attach, 'is_inline', False)),
                        },
                    )
                except Exception as e:
                    logger.error(f"Ошибка создания записи вложения {attach.filename}: {e}")

    # Ошибки разорванного соединения: сервер (Яндекс) периодически отвечает
    # `BYE problems with connection` — и посреди FETCH больших писем (~30 МБ),
    # и уже на этапе CAPABILITY/LOGIN. Это транзиентное: лечится паузой
    # и повтором, а не падением всего прогона.
    _CONN_ERRORS = (
        imaplib.IMAP4.abort,
        imaplib.IMAP4.error,
        ConnectionError,
        TimeoutError,
        OSError,
    )

    IMAP_TIMEOUT = 60

    #: Сколько раз пробуем войти при обрыве соединения и паузы между попытками.
    LOGIN_RETRIES = 3
    LOGIN_RETRY_DELAYS = (5, 15)

    def _login(self, folder: str) -> MailBox:
        """Подключается к IMAP (без with — чтобы можно было переподключаться)."""
        return MailBox(YA_HOST, timeout=self.IMAP_TIMEOUT).login(
            YA_USER, YA_PASSWORD, initial_folder=folder
        )

    def _login_with_retry(self, folder: str) -> MailBox:
        """Вход с ретраями: Яндекс регулярно рвёт соединение (BYE).

        Последняя ошибка пробрасывается наружу — её классифицирует вызывающий
        код (транзиентная -> warning без traceback, прочая -> exception).
        """
        last_exc = None
        for attempt in range(1, self.LOGIN_RETRIES + 1):
            try:
                return self._login(folder)
            except self._CONN_ERRORS as e:
                last_exc = e
                if attempt < self.LOGIN_RETRIES:
                    delay = self.LOGIN_RETRY_DELAYS[min(attempt - 1, len(self.LOGIN_RETRY_DELAYS) - 1)]
                    logger.warning(
                        f"IMAP ({folder}): вход {attempt}/{self.LOGIN_RETRIES} "
                        f"не удался ({e}), повтор через {delay} c..."
                    )
                    time.sleep(delay)
        raise last_exc

    @staticmethod
    def _logout_quietly(mailbox) -> None:
        try:
            mailbox.logout()
        except Exception:
            pass

    def _process_message(self, msg, email_type: str) -> None:
        """Сохраняет одно уже скачанное письмо в БД и на диск."""
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

    def _save_headers_only(self, mailbox, email_type: str, uid: str) -> None:
        """Сохраняет письмо-«тяжеловес» только по заголовкам.

        Тело таких писем сервер не отдаёт (рвёт соединение), но UID нужно
        зафиксировать в БД — иначе письмо будет ронять каждый запуск
        и блокировать обработку более старых писем.

        mark_seen=False: сам факт загрузки не должен помечать письмо
        прочитанным на сервере (BODY.PEEK вместо BODY).
        """
        try:
            msgs = list(mailbox.fetch(AND(uid=uid), headers_only=True, mark_seen=False))
        except Exception as e:
            logger.error(f"Не удалось получить даже заголовки письма {uid}: {e}")
            self.error_list.append(uid)
            return
        if not msgs:
            logger.error(f"Письмо {uid} не найдено на сервере")
            self.error_list.append(uid)
            return

        msg = msgs[0]
        self.create_action_list.append(msg.uid)
        try:
            message = EmailImapMessage(self.root_folder_path, msg)
            self._create_folder(message.folder_path_name)
            message.save_e_mail_to_html()

            serializer = DbEmailImapMessageSerializer(
                email_type, message.folder_path_name, msg
            )
            email_obj = serializer.create_record()
            note = (
                "[Служебная пометка: тело письма не загружено — сервер "
                "разрывает соединение при скачивании "
                f"(размер ~{msg.size or 0} байт). Сохранены только заголовки.]"
            )
            email_obj.body_text = f"{note}\n\n{email_obj.body_text or ''}".strip()
            email_obj.save(update_fields=['body_text'])
        except Exception as e:
            logger.exception(f"Ошибка сохранения заголовков письма {msg.uid}: {e}")
            self.error_list.append(msg.uid)

    def _sync_seen_to_db(self, mailbox, folder_db: str) -> int:
        """Подтягивает серверные \\Seen в локальные is_read (только False -> True).

        Письмо, прочитанное на сервере (веб/телефон), не должно висеть
        «непрочитанным» в приложении. Обратное направление (снятие флага)
        здесь запрещено — локальное «прочитано» повторной загрузкой
        не сбрасывается.
        """
        try:
            seen_uids = set(mailbox.uids(AND(seen=True)))
        except Exception as e:
            logger.warning(f"Не удалось получить Seen-список ({folder_db}): {e}")
            return 0
        if not seen_uids:
            return 0
        try:
            updated = Email.objects.filter(
                folder=folder_db, uid__in=list(seen_uids), is_read=False,
            ).update(is_read=True)
            if updated:
                logger.info(f"IMAP ({folder_db}): помечено прочитанными по Seen: {updated}")
            return updated
        except Exception as e:
            logger.warning(f"Не удалось sync Seen -> is_read ({folder_db}): {e}")
            return 0

    def main(self, email_type: str, folder: str, limit: Optional[int] = None) -> None:
        """Основной метод: подключается к IMAP и обрабатывает письма.

        Устойчив к обрывам соединения: сначала получает лёгкий список UID
        и качает только новые письма, по одному. При обрыве — переподключение
        и повтор; письмо, которое сервер не отдаёт целиком, сохраняется
        по заголовкам и больше не блокирует очередь.

        mark_seen=False везде: проверка почты не должна менять флаги
        на сервере (раньше каждый fetch молча ставил \\Seen всем
        скачанным письмам).
        """
        folder_db = 'inbox' if email_type == 'IN' else 'sent'
        existing_uids = self._get_existing_uids(folder_db)

        mailbox = None
        try:
            mailbox = self._login_with_retry(folder)
            all_uids = mailbox.uids()
            window_uids = all_uids[-limit:] if limit is not None else list(all_uids)
            new_uids = [uid for uid in window_uids if uid not in existing_uids]
            self.skip_action_list.extend(uid for uid in window_uids if uid in existing_uids)
            logger.info(
                f"IMAP ({folder}): всего {len(all_uids)}, новых {len(new_uids)}"
            )

            # Seen -> is_read для уже загруженных (прочитали на сервере —
            # должно стать прочитанным и у нас).
            try:
                self._sync_seen_to_db(mailbox, folder_db)
            except Exception:
                logger.exception("Ошибка sync Seen -> is_read")

            for uid in new_uids:
                try:
                    msgs = list(mailbox.fetch(AND(uid=uid), mark_seen=False))
                except self._CONN_ERRORS:
                    logger.warning(
                        f"Обрыв соединения на письме {uid}, переподключаюсь..."
                    )
                    self._logout_quietly(mailbox)
                    try:
                        mailbox = self._login_with_retry(folder)
                        msgs = list(mailbox.fetch(AND(uid=uid), mark_seen=False))
                    except self._CONN_ERRORS as e2:
                        logger.warning(
                            f"Письмо {uid} не отдаётся целиком ({e2}), "
                            "сохраняю заголовки"
                        )
                        self._save_headers_only(mailbox, email_type, uid)
                        continue
                if not msgs:
                    continue
                self._process_message(msgs[0], email_type)

        except self._CONN_ERRORS as e:
            # Транзиентный обрыв (типично: BYE problems with connection):
            # штатная ситуация, не ошибка кода — warning без traceback.
            # Папка пропускается, следующий прогон (или ретрай) её доберёт.
            logger.warning(f"IMAP ({folder}): нет соединения с сервером ({e}) — пропускаю")
            self.error_list.append(f'IMAP connection ({folder}): {e}')
        except Exception as e:
            logger.exception(f"Ошибка подключения к IMAP ({folder}): {e}")
            self.error_list.append(f'IMAP connection ({folder}): {e}')
        finally:
            if mailbox is not None:
                self._logout_quietly(mailbox)
