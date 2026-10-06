# findings — Блок 1

## Решения владельца — выполнено (pushed f014d7e), кроме п.1
1. SECRET_KEY — НЕ НУЖНО (пропущено по команде).
2. DONE: неизвестное условие правила — fail-closed.
3. Двойной журнал ContractAdmin — проверено: дубля нет (сигналы журнала
   по договорам отсутствуют; save/delete пишут по одной записи — гарды B7).
   Отдельного фикса не требует.
4. DONE: bulk_create привязок валидирует clean (люк skip_validation).
5. DONE: вложения без link — fallback sent/<id>.
6. DONE: кириллический поиск — casefold-добор.
7. DONE: filter_panel — функция восстановлена (авто-открытие модалки).

## Внимание (не моё, требует взгляда)
- makemigrations --check: незафиксированное изменение DocRegistry
  (0015 alter change_descr) — из твоих незакоммиченных правок моделей.

## Инфра
- БД: `DB_DIR = <parent>/djangoProjectDB`, `DATABASES.default.NAME = djangoProjectDB/db.sqlite3` (`djangoProject/settings.py:181-186`). Локальный `db.sqlite3` (0 байт) не используется.
- Тесты: только `manage.py test`, pytest/requirements нет.
- `manage.py test` без `PYTHONUTF8=1` падает в `DocRegistry/migrations/0010_split_registries.py:22` (print со стрелкой, cp1251).
- Проверено: `email_ui.tests.UtilsTest` 9/9 OK с `PYTHONUTF8=1`.
- Существующие: `ProjectTDL/Tests/` (5 файлов), `ProjectContract/tests.py`, `DocRegistry/tests.py`, `email_ui/tests.py`.
