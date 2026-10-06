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

## Вердикты B1–B8 — выполнено (блоки 27–31)
- B1 DONE (27): compose-поток -> compose_flow.
- B2 DONE (28): thread-хелперы -> thread_service.
- B3 DONE (26): дубль декоратора снят.
- B4 DONE (31): _save_modal_form (фабрика CBV отклонена — см. план).
- B5 DONE (26): запятая делится.
- B6 DONE (30): push_seen_async (daemon-поток).
- B7 DONE (29): фазы custom_task_view -> task_view.
- B8 DONE (30): гард фан-аута (дублей нет).

## Предложения по бизнес-логике и кодовой базе (Блок 25, ждут вердикта)
- B1: compose-тройник (views 1309/1388/1545: send/reply_send/draft_send
  75–118 строк) -> services/compose_flow.py поверх compose_service.
- B2: thread-хелперы (_attach_thread_context/_build_thread_list/
  _build_selection_threads) -> thread_service (3 ленивых импорта там же).
- B3: draft_update: двойной @login_required (views 1710–1713) — снять дубль.
- B4: ~40 CRUD-вьюх контактов/групп/тегов/правил/фильтров -> CBV-миксин.
- B5: _get_list_from_request: ветка split(',') недостижима — чинить/удалить.
- B6: _push_seen_to_server ходит в IMAP синхронно из запроса — в фон/очередь.
- B7: custom_task_view 157 строк (ProjectTDL/views 85) -> фазы в services.
- B8: нет гарда на комбинацию tags+has_attachments (JOIN-фан-аут) в filter_emails.
- MCP: roslyn-graph — только C# (к Django неприменим); ast-grep MCP-сервер
  заперт на cwd HeatLossRevit4, но бинарь 0.43.0 работает для Python через
  shell (проверено) — запахи следующих блоков им.

## Внимание (не моё, требует взгляда)
- makemigrations --check: незафиксированное изменение DocRegistry
  (0015 alter change_descr) — из твоих незакоммиченных правок моделей.

## Инфра
- БД: `DB_DIR = <parent>/djangoProjectDB`, `DATABASES.default.NAME = djangoProjectDB/db.sqlite3` (`djangoProject/settings.py:181-186`). Локальный `db.sqlite3` (0 байт) не используется.
- Тесты: только `manage.py test`, pytest/requirements нет.
- `manage.py test` без `PYTHONUTF8=1` падает в `DocRegistry/migrations/0010_split_registries.py:22` (print со стрелкой, cp1251).
- Проверено: `email_ui.tests.UtilsTest` 9/9 OK с `PYTHONUTF8=1`.
- Существующие: `ProjectTDL/Tests/` (5 файлов), `ProjectContract/tests.py`, `DocRegistry/tests.py`, `email_ui/tests.py`.
