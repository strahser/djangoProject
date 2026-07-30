import os
import threading

_thread_local = threading.local()


def get_current_db():
    val = getattr(_thread_local, 'current_db', None)
    if val is not None:
        return val
    return os.environ.get('DB_MODE', 'default')


def set_current_db(db_alias):
    _thread_local.current_db = db_alias


def unset_current_db():
    if hasattr(_thread_local, 'current_db'):
        del _thread_local.current_db
