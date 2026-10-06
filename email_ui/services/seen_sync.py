"""Блок 30 (B6): фоновая синхронизация Seen (вынесено из views.py 1:1).

_push_seen_to_server ходил в IMAP синхронно из запроса (открытие/прочтение/
bulk): каждый клик ждал login+STORE+logout. Теперь views зовут
push_seen_async — тот же best-effort код в daemon-потоке, запрос не ждёт
сеть. Поток трогает только атрибуты писем/настройки (без запросов в БД).
"""
from loguru import logger

#: Локальная папка БД -> имя папки на IMAP-сервере (обратное к scheduled/fetch).
IMAP_FOLDER_BY_DB = {'inbox': 'INBOX', 'sent': 'Отправленные'}


def push_seen_to_server(email_or_emails, seen=True):
    """Best-effort синхронизация локального is_read -> серверный \\Seen.

    Прочитанное в приложении должно стать прочитанным и на сервере,
    иначе веб/телефон продолжат показывать его непрочитанным и следующая
    загрузка (Seen -> БД) будет спорить с локальным статусом.
    Ошибки сети/авторизации глушатся: UI не должен падать из-за IMAP.
    """
    try:
        items = list(email_or_emails) if isinstance(email_or_emails, (list, tuple, set)) else [email_or_emails]
    except TypeError:
        items = [email_or_emails]
    by_folder = {}
    for email in items:
        try:
            uid = (email.uid or '').strip()
        except Exception:
            uid = ''
        # На сервер отправляем только настоящие IMAP-UID (цифры).
        # Тестовые ('bulk-uid-1'), legacy (Message-ID как uid) и пустые —
        # сервер их не знает, STORE вернёт ошибку.
        if not uid or not uid.isdigit():
            continue
        imap_folder = IMAP_FOLDER_BY_DB.get(getattr(email, 'folder', ''))
        if not imap_folder:
            continue  # drafts/archive/trash — локальные, на сервере их нет
        by_folder.setdefault(imap_folder, []).append(uid)
    if not by_folder:
        return
    try:
        from django.conf import settings as dj_settings
        host = getattr(dj_settings, 'YA_HOST', '') or ''
        user = getattr(dj_settings, 'YA_USER', '') or ''
        password = getattr(dj_settings, 'YA_PASSWORD', '') or ''
        if not (host and user and password):
            return
        from imap_tools import MailBox
        timeout = int(getattr(dj_settings, 'EMAIL_IMAP_TIMEOUT', 20) or 20)
        for imap_folder, uids in by_folder.items():
            mailbox = None
            try:
                mailbox = MailBox(host, timeout=timeout).login(user, password, initial_folder=imap_folder)
                mailbox.flag(uids, '\\Seen', seen)
            except Exception as e:
                logger.warning(f"IMAP push Seen={seen} ({imap_folder}, {len(uids)} шт.): {e}")
            finally:
                try:
                    if mailbox is not None:
                        mailbox.logout()
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"IMAP push Seen: {e}")


def push_seen_async(email_or_emails, seen=True):
    """Тот же push в daemon-потоке: запрос не ждёт сеть (B6).

    Возвращает поток (тестам — join для детерминированности).
    """
    import threading
    thread = threading.Thread(
        target=push_seen_to_server, args=(email_or_emails, seen),
        name='imap-push-seen', daemon=True)
    thread.start()
    return thread
