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
            parser = ParsingImapEmailToDB(root_path)
            parser.main(email_type, folder, limit=AUTO_FETCH_LIMIT)
            created.extend(parser.create_action_list)
            skipped.extend(parser.skip_action_list)
            errors.extend(parser.error_list)

        logger.info(
            f"[EmailAutoFetch] Загрузка завершена: новых {len(created)}, "
            f"пропущено {len(skipped)}, ошибок {len(errors)}"
        )
        if created:
            logger.info(f"[EmailAutoFetch] Новые письма: {created[:50]}")
    except Exception as exc:
        logger.exception(f"[EmailAutoFetch] Ошибка при загрузке почты: {exc}")
    finally:
        try:
            close_old_connections()
        except Exception:
            pass


def start_email_fetch_scheduler():
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
        logger.info(
            f"[EmailAutoFetch] Планировщик запущен (каждые {settings.EMAIL_FETCH_INTERVAL_MINUTES} минут)"
        )
    except Exception as exc:
        logger.exception(f"[EmailAutoFetch] Не удалось запустить планировщик: {exc}")
