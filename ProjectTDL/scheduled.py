import os
import shutil
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from djangoProject.settings import BASE_DIR, AUTOSAVE_PERIOD, BACKUP_PATH, DB_DIR
from pathlib import Path
def make_db_backup():
	now = datetime.datetime.now()
	timestamp = str(now.strftime("%Y_%m_%d_%H_%M_%S"))
	src = os.path.join(DB_DIR, 'db.sqlite3') / 'db.sqlite3'
	Path(BACKUP_PATH).mkdir(parents=True, exist_ok=True)
	dest = f"{BACKUP_PATH}/{timestamp}_db_backup.sqlite3"
	shutil.copy(src, dest)
	logger.info(f'copy successful to{dest}')
def start_task():
	scheduler = BackgroundScheduler()
	scheduler.add_job(make_db_backup, 'interval', minutes=AUTOSAVE_PERIOD)
	scheduler.start()
