import datetime
import os

from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django.db import close_old_connections
from loguru import logger

from Emails.models import EmailType
from Emails.ЕmailParser.EmailConfig import E_MAIL_DIRECTORY
from Emails.ЕmailParser.ParsingImapEmailToDB import ParsingImapEmailToDB

AUTO_FETCH_LIMIT = 100

# Защита от двойного запуска: runserver с autoreload и повторные вызовы
# из apps.ready() создавали 2-3 параллельных планировщика, которые
# одновременно качали одни и те же UID (в логах — парные прогоны
# «новых 6» + «новых 2» с теми же UID и гонка записей).
_SCHEDULER_STARTED = False


def fetch_new_emails_job():
    """Автоматическая загрузка новых писем из IMAP (каждые 30 минут)."""
    try:
        close_old_connections()
    except Exception:
        pass

    directory = os.path.join(E_MAIL_DIRECTORY, 'imap_attachments')
    folders = {
        'INBOX': EmailType.IN.name,
        'Отправленные': EmailType.OUT.name,
    }

    created = []
    skipped = []
    errors = []

    try:
        for folder, email_type in folders.items():
            root_path = os.path.join(directory, folder)
            try:
                parser = ParsingImapEmailToDB(root_path)
                parser.main(email_type, folder, limit=AUTO_FETCH_LIMIT)
            except Exception as exc:
                # Падение одной папки не отменяет вторую (как в fetch_emails).
                errors.append(f'{folder}: {exc}')
                continue
            created.extend(parser.create_action_list)
            skipped.extend(parser.skip_action_list)
            errors.extend(parser.error_list)

        logger.info(
            f"[EmailAutoFetch] Загрузка завершена: новых {len(created)}, "
            f"пропущено {len(skipped)}, ошибок {len(errors)}"
        )
        if created:
            logger.info(f"[EmailAutoFetch] Новые письма: {created[:50]}")
        if errors:
            # Транзиентные обрывы (BYE problems with connection) — warning,
            # а не exception: сервер Яндекса регулярно рвёт соединения,
            # следующий прогон доберёт пропущенное.
            logger.warning(f"[EmailAutoFetch] Ошибки прогона: {errors[:10]}")
    except Exception as exc:
        logger.exception(f"[EmailAutoFetch] Ошибка при загрузке почты: {exc}")
    finally:
        try:
            close_old_connections()
        except Exception:
            pass


def start_email_fetch_scheduler():
    global _SCHEDULER_STARTED
    if _SCHEDULER_STARTED:
        logger.warning("[EmailAutoFetch] Планировщик уже запущен — повторный старт пропущен")
        return
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            fetch_new_emails_job,
            'interval',
            minutes=settings.EMAIL_FETCH_INTERVAL_MINUTES,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.datetime.now(),
        )
        scheduler.start()
        _SCHEDULER_STARTED = True
        logger.info(
            f"[EmailAutoFetch] Планировщик запущен (каждые {settings.EMAIL_FETCH_INTERVAL_MINUTES} минут)"
        )
    except Exception as exc:
        logger.exception(f"[EmailAutoFetch] Не удалось запустить планировщик: {exc}")
