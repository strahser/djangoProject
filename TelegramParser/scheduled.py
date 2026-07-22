import sys
import threading
import traceback
from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger


def _log(msg):
    print(f"[TGParser-Scheduler] {msg}", flush=True)
    sys.stdout.flush()


def _run_parse_in_thread(channel_username):
    from .parser import parse_channel

    def _target():
        try:
            _log(f"Старт по расписанию: {channel_username}")
            parse_channel(channel_username, incremental=True)
            _log(f"Завершено по расписанию: {channel_username}")
        except Exception as e:
            _log(f"ОШИБКА по расписанию {channel_username}: {e}")
            _log(traceback.format_exc())

    thread = threading.Thread(target=_target, daemon=True, name=f"TGParser-Sched-{channel_username}")
    thread.start()
    return thread


def run_weekly_parse():
    from .models import TelegramChannel

    _log("Еженедельный запуск парсинга")
    channels = TelegramChannel.objects.filter(is_active=True)
    for ch in channels:
        _run_parse_in_thread(ch.username)


def start_telegram_scheduler():
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(run_weekly_parse, 'interval', weeks=1)
        scheduler.start()
        _log("Планировщик запущен (1 раз/неделю)")
    except Exception as e:
        _log(f"Не удалось запустить планировщик: {e}")
