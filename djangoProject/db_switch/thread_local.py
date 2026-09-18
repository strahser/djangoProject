import os
import threading

_thread_local = threading.local()


def get_current_db():
    val = getattr(_thread_local, 'current_db', None)
    if val is not None:
        return val
    # Нормализация: принимают и короткие имена режимов, и алиасы БД.
    # Без этого DB_MODE=personal давал несуществующий алиас 'personal'
    # (миграции писались в django_migrations без применения схемы).
    mode = os.environ.get('DB_MODE', 'default')
    return {'personal': 'personal_db', 'work': 'default'}.get(mode, mode)


def set_current_db(db_alias):
    _thread_local.current_db = db_alias


def unset_current_db():
    if hasattr(_thread_local, 'current_db'):
        del _thread_local.current_db
