# findings — Блок 1

## Решения владельца (ожидают вердикта, не трогать без команды)
1. SECRET_KEY в истории git — ротация через DJANGO_SECRET_KEY (разлогинит всех).
2. Неизвестное условие email-правила игнорируется (= правило срабатывает всегда).
3. Двойной журнал ContractAdmin save/delete vs API log_change — зафиксировано как факт.
4. PaymentTaskLink.clean обходится через bulk_create (переплата без ошибки) — факт.
5. Вложения писем без link теряются молча (file_path='') — факт.
6. SQLite LIKE регистронезависим только для ASCII (кириллический поиск чувствителен).
7. test_filter_panel_opens_when_filters_active падает (чужие незакоммиченные правки шаблонов).

## Инфра
- БД: `DB_DIR = <parent>/djangoProjectDB`, `DATABASES.default.NAME = djangoProjectDB/db.sqlite3` (`djangoProject/settings.py:181-186`). Локальный `db.sqlite3` (0 байт) не используется.
- Тесты: только `manage.py test`, pytest/requirements нет.
- `manage.py test` без `PYTHONUTF8=1` падает в `DocRegistry/migrations/0010_split_registries.py:22` (print со стрелкой, cp1251).
- Проверено: `email_ui.tests.UtilsTest` 9/9 OK с `PYTHONUTF8=1`.
- Существующие: `ProjectTDL/Tests/` (5 файлов), `ProjectContract/tests.py`, `DocRegistry/tests.py`, `email_ui/tests.py`.
