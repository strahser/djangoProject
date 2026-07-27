import os
import re
import shutil
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from djangoProject.settings import BASE_DIR, AUTOSAVE_PERIOD, BACKUP_PATH, DB_DIR, BACKUP_KEEP_VERSIONS
from pathlib import Path


def _cleanup_old_backups(keep=BACKUP_KEEP_VERSIONS):
    backup_dir = Path(BACKUP_PATH)
    if not backup_dir.exists():
        return

    files = []
    for f in backup_dir.iterdir():
        if f.is_file() and f.name.endswith('_db_backup.sqlite3'):
            files.append(f)

    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    for f in files[keep:]:
        try:
            f.unlink()
            logger.info(f'removed old backup: {f.name}')
        except Exception as e:
            logger.warning(f'failed to remove {f.name}: {e}')


def make_db_backup():
    now = datetime.datetime.now()
    timestamp = str(now.strftime("%Y_%m_%d_%H_%M_%S"))
    src = os.path.join(DB_DIR, 'db.sqlite3')

    Path(BACKUP_PATH).mkdir(parents=True, exist_ok=True)
    dest = f"{BACKUP_PATH}/{timestamp}_db_backup.sqlite3"
    shutil.copy(src, dest)
    logger.info(f'copy successful to{dest}')

    _cleanup_old_backups()


def start_task():
    scheduler = BackgroundScheduler()
    scheduler.add_job(make_db_backup, 'interval', minutes=AUTOSAVE_PERIOD)
    scheduler.start()
