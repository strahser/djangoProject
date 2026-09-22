import os
import re
import shutil
import sqlite3
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from djangoProject.settings import BASE_DIR, AUTOSAVE_PERIOD, BACKUP_PATH, DB_DIR, BACKUP_KEEP_VERSIONS
from pathlib import Path


# БД, которые бэкапим: (имя файла БД или абсолютный путь, шаблон имени бэкапа).
# Личная БД живёт в отдельном проекте DjangoProjectPersonal.
BACKUP_TARGETS = (
    ('db.sqlite3', '{ts}_db_backup.sqlite3'),
    (r'E:\Автоматизация\DjangoProjectPersonal\db.sqlite3', '{ts}_personal_db_backup.sqlite3'),
)


# Суффиксы имён бэкапов для ротации — строго раздельно по БД
# (суффикс рабочей БД является окончанием суффикса личной, поэтому
# простым endswith их различать нельзя).
BACKUP_SUFFIXES = ('_db_backup.sqlite3', '_personal_db_backup.sqlite3')


def _cleanup_old_backups(keep=BACKUP_KEEP_VERSIONS):
    backup_dir = Path(BACKUP_PATH)
    if not backup_dir.exists():
        return

    for suffix in BACKUP_SUFFIXES:
        if suffix == '_db_backup.sqlite3':
            files = [f for f in backup_dir.iterdir()
                     if f.is_file() and f.name.endswith(suffix)
                     and not f.name.endswith('_personal_db_backup.sqlite3')]
        else:
            files = [f for f in backup_dir.iterdir()
                     if f.is_file() and f.name.endswith(suffix)]
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files[keep:]:
            try:
                f.unlink()
                logger.info(f'removed old backup: {f.name}')
            except Exception as e:
                logger.warning(f'failed to remove {f.name}: {e}')


def _sqlite_backup(src_path, dest_path):
    """Консистентный бэкап через sqlite3 backup API (корректно при WAL)."""
    src = sqlite3.connect(f'file:{src_path}?mode=ro', uri=True, timeout=30)
    try:
        dst = sqlite3.connect(str(dest_path), timeout=30)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def make_db_backup():
    now = datetime.datetime.now()
    timestamp = str(now.strftime("%Y_%m_%d_%H_%M_%S"))
    Path(BACKUP_PATH).mkdir(parents=True, exist_ok=True)
    for src_name, pattern in BACKUP_TARGETS:
        src = src_name if os.path.isabs(src_name) else os.path.join(DB_DIR, src_name)
        if not os.path.exists(src):
            logger.warning(f'backup source missing, skip: {src}')
            continue
        dest = os.path.join(BACKUP_PATH, pattern.format(ts=timestamp))
        try:
            _sqlite_backup(src, dest)
            logger.info(f'copy successful to {dest}')
        except Exception as e:
            logger.error(f'backup failed for {src}: {e}')

    _cleanup_old_backups()


def start_task():
    scheduler = BackgroundScheduler()
    scheduler.add_job(make_db_backup, 'interval', minutes=AUTOSAVE_PERIOD)
    scheduler.start()
