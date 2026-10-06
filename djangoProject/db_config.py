"""SQLite-прагмы проекта (блок 32): WAL + busy timeout.

Прод — один файл SQLite, писателей несколько (веб, fetch_emails,
планировщик): без WAL читатели блокируются писателем, без timeout
первый же конфликт — OperationalError «database is locked».
Подключается импортом в djangoProject/__init__.py.
"""
from django.db.backends.signals import connection_created

BUSY_TIMEOUT_MS = 20000


def _configure_sqlite(sender, connection, **kwargs):
    if connection.vendor != 'sqlite':
        return
    with connection.cursor() as cur:
        cur.execute('PRAGMA journal_mode=WAL')
        cur.execute(f'PRAGMA busy_timeout={BUSY_TIMEOUT_MS}')
        cur.execute('PRAGMA synchronous=NORMAL')


connection_created.connect(
    _configure_sqlite, dispatch_uid='djangoProject.sqlite-pragmas')
