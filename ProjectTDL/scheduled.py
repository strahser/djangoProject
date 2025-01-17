import shutil
import datetime
import os
from apscheduler.schedulers.background import BackgroundScheduler
from djangoProject.settings import BASE_DIR, AUTOSAVE_PERIOD, BACKUP_PATH
from pathlib import Path
def make_db_backup():
	now = datetime.datetime.now()
	timestamp = str(now.strftime("%Y_%m_%d_%H_%M_%S"))
	src = BASE_DIR / 'db.sqlite3'
	Path(BACKUP_PATH).mkdir(parents=True, exist_ok=True)
	dest = f"{BACKUP_PATH}/{timestamp}_db_backup.sqlite3"
	shutil.copy(src, dest)
	print(f'copy successful to{dest}')
def start_task():
	scheduler = BackgroundScheduler()
	scheduler.add_job(make_db_backup, 'interval', minutes=AUTOSAVE_PERIOD)
	scheduler.start()
