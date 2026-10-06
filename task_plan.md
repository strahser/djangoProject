# Блок 27 (B1): compose-поток views -> services/compose_flow (in progress)

# Блок 26: B3+B5 (done, pushed 2842e24)

B3: дубль декоратора draft_update снят (auth-гард в tests_fixes_b26).
B5: _get_list_from_request делит запятые (докстринг так обещал):
'tag=a,b' -> ['a','b'], смешанные 'tag=1,a&tag=b,,c' плоско. Тесты B25
обновлены. Проверка: 41/41 OK (b25+b26+DraftUpdateViewTest).

# Блок 25: чистые хелперы email_ui/views -> services (done)

views.py 2806 -> 2525 (-281): токены/Q/filter_emails ->
`email_ui/services/query_service.py` (201); сортировка/навигация
(_sanitize_next_url, _clean_query_string, _build_back_url, _safe_next,
_get_list_from_request, apply_sorting + ALLOWED_SORT_FIELDS) ->
`email_ui/services/navigation.py` (102). Тела 1:1, views — re-export
(patch-таргеты `email_ui.views.*` и ленивый импорт из Emails/views целы).
Тесты `email_ui/tests_views_b25.py` 36/36 (факты+quirks: запятая в
_get_list_from_request не делится; ORDER BY рендерится DESC).
Проверка: email_ui 317/317 OK (235s), manage check clean.

# Блок 24: таблица подзадач формы правки (done, pushed 50e8373)

# ФИНАЛ автопилота (2026-10-06): полный прогон 603 теста — 602 OK,
# 1 pre-existing filter_panel (чужие правки). manage.py check: no issues.
# Открытые вердикты владельца — в findings.md (7 шт).

subtask_actions_html() в Tables.py, тонкий get_context_data.
Тесты TaskUpdateViewTest 2/2. ProjectTDL 112/112 OK.

# Блок 23: FK-префетч в changelist (done, pushed 515deb0)

get_queryset select_related в обеих админках; гард 0 запросов на FK +
smoke рендера tasknode-changelist. 18/18 OK.

# Блок 22: матрица drift-сверки (done, pushed c697ecf)

compare_registry — 3 теста чистой функции. DocRegistry 67/67 OK.

# Блок 21: task_ids отчёта санитизированы (done, pushed a09b87b)

Мусор в ?task_ids= давал 500 на id__in — отбрасывается. +5 тестов
(CustomReportViewTest). test_reports_b6 15/15 OK.

# Блок 20: TelegramParser (done, pushed 05e7439)

Вьюхи под login_required; битый id -> 404; fallback-редирект на changelist
(был redirect('admin') -> 500). Юниты экстракторов/важности/вьюх 10/10.

# Блок 19: юниты сервисов email_ui (done, pushed e8c0035)

RuleEvaluator/ContactService/ThreadService — 10/10. Зафиксирован факт:
неизвестное условие правила игнорируется (= правило срабатывает) —
менять только решением владельца.

# Блок 18: владение в подзадачах и bulk-удалении (done, pushed dde0a6f)

quick_create_subtask + inline в карточке: только залогированным к своим
(был 500 анониму и запись на чужие); bulk_delete: auth + только свои id
(было удаление всего без логина). +7 гардов. ProjectTDL 104/104 OK.

# Блок 17: разрыв цикла админок (done, pushed 6deab7f)

StaticData/admin: локальный excluding_list вместо импорта ProjectTDL.admin
(состав реестра тот же). Тесты tests_admin_b17.py. StaticData 6/6 OK.

# Блок 16: мёртвые мутаторы дат удалены (done, pushed 9c190fd + фикс 2e6a9dd)

update_due_date/update_start_date без вызывающих убраны; update_children —
гард делегирования. Урок: коммит только после зелёного прогона.
ProjectContract 127/127 OK.

# Блок 15: защита удаления справочников (done, pushed f1f2eb7)

manage_reference delete проверяет использование (задачи+договоры):
каскадный снос проекта/подрядчика, 500 по статусу и молчаливый unlink
категории заблокированы с сообщением. ProjectTDL 97/97 OK.

# Блок 14: автозагрузка переживает падение папки (done, pushed 97c6230)

Та же болезнь, что в fetch_emails: per-folder try/except в errors.
Тесты ScheduledFetchTest 2/2, весь F2-файл 20/20 OK.

# Блок 13: пустые пивоты — заглушки (done, pushed bd94a72)

Прод-ошибки 13:50 (KeyError contract__id/payment_value при договорах без
платежей): пусто -> None/заглушки + df_total=0, без ERROR-логов. Тело пивота
в _pivot_contract_table. Тесты tests_guards_b13.py 5/5.
ProjectContract 126/126 OK.

# Хотфикс: fetch_emails 500 (done, pushed f8f4ef9, 2026-10-06)

Жалоба: ошибка получения почты на /email-ui/folder/inbox/. Рендер — 200,
падал fetch: мусор в mail_count (int() -> 500, воспроизведено вживую) +
падение одной IMAP-папки роняло всё. Фикс: дефолт+кламп, try/except по
папкам в error_list. Тесты FetchGuardsTest 3/3. Проверено вживую на :8000
с боевой БД: мусор -> 302. Свой dev-сервер после проверки остановлен.

# Блок 12: карточка задачи (done, pushed f175bd6)

Гарды рендера + счётчик 12 (N+1 нет — проверено попыткой select_related
с нулевой дельтой, откачено). Прод-код не менялся, только тесты.

# Блок 11: изоляция М1/К1 (done, pushed 911d53e)

Гарды: состав m1_site/k1_site без чужих моделей, общие в обоих;
smoke админок + редирект анониму; очереди видят только своё.
Права уже были корректны (login_required/IsAuthenticated) — только пины.
Тесты tests_guards_b11.py 6/6.

# Блок 10: справочники email_ui (done, pushed 8bdbd72)

contact_search без N+1 (prefetch+cache, гард 4 запроса); bulk_assign_tag
пачкой с ignore_conflicts; assign_tag мусор -> 400 (был 500). Тесты
tests_guards_b10.py 10/10 + Contact/Tag suites 17/17.

# Блок 9: настройки через env (done, pushed 2c80354)

SECRET_KEY/DEBUG/ALLOWED_HOSTS/MEDIA_ROOT/BACKUP_PATH — из окружения,
дефолты те же. DevAutoLogin DEBUG-gated (зафиксировано тестом).
Тесты tests_settings_b9.py 3/3. Прод-ротация ключа — отдельным решением
(ключ в истории git, смена разлогинит всех).

# Блок 8: баги гардов закрыты (done, pushed 54f17a3)

update_task_field owner-only + запятая; история сроков = request.user;
SubTaskCloneView fallback; 5 мутаций в atomic. Гарды F1 обновлены под
намеренное поведение + тест атрибуции. ProjectTDL 91/91 OK.

# Блок 7: админка договоров (done, pushed c4d64b5)

Агрегаты changelist 3->2 (гардом пойман fan-out JOIN при объединении в 1 —
разделено корректно); строки paid/unpaid через аннотации (4 запроса/строку
-> 0, фолбэк legacy); пустая выдача None-safe (был TypeError/500).
Журнал save/delete зафиксирован тестами (SET_NULL переживает удаление).
Тесты tests_guards_b7.py 6/6. ProjectContract 121/121 OK.

# Блок 6: reports.py гигиена + гарды (done, pushed aff52ff)

Bare except -> typed; select_related('status') у детей протокола (5->4 запроса).
Тесты test_reports_b6.py 10/10. ProjectTDL 89/89 OK.

# Блок 5: админка задач -> services (done, pushed 28c8453)

services/admin_reports.py: report_action_response + build_admin_return_url.
Экшены — 3 строки; удалён мёртвый email_list; save_model: silent except ->
warning в лог. Тесты test_admin_b5.py 10/10. ProjectTDL 79/79 OK.

# Блок 4: фильтры + bulk ProjectTDL -> services (done 2026-10-06)

Новый пакет `ProjectTDL/services/`: task_filters.py (inherit_filter_q,
task_subtree_qs, get_filter_state, cascade_options) + task_mutations.py
(parse_bulk_updates, apply_bulk_update в транзакции, create_task_with_defaults).
Views: тонкие обёртки (импорты тестов из views работают), bulk/quick/cascade
делегируют. Поведение 1:1 (молчаливый скип невалида, запятая в цене bulk,
суммарный аудит, наследование от last_task).
Проверка: ProjectTDL 69/69 OK с первого прогона (54 старых + 15 новых
test_task_services_b4.py).

# Блок 3: тройник отправки -> compose_service (done 2026-10-06)

Новый `email_ui/services/compose_service.py` (~200 строк, юниты в F2):
parse_recipients / invalid_addresses / build_sender / create_sent_email /
persist_uploaded_files / copy_attachment_rows / parse_excluded_ids.
Views send/reply/draft_send — тонкие (формы, фолбэки, шаблоны), поведение 1:1
включая BUG draft compose_modal (помечен в коде).
Проверка: 33/33 целевых OK; полный email_ui 255 тестов — только известный
pre-existing filter_panel. Файлы: services/compose_service.py (new),
views.py (send/reply/draft), tests_guards_f2.py (+ComposeServiceTest).

# Блок 2: N+1 в TaskNodeTable (done 2026-10-06)

Решение: `annotate_has_children()` (EXISTS) в `_task_subtree_qs` — одна точка,
покрывает custom_task_view + filter_tasks_ajax (+ids/export harmless).
`render_name`/`row_attrs` читают аннотацию, фолбэк exists() для таблиц вне qs.
Файлы: `ProjectTDL/Tables.py` (annotate_has_children, _record_has_children),
`ProjectTDL/views.py` (_task_subtree_qs), гард обновлён (0 запросов + фолбэк 4).
Проверка: ProjectTDL 54/54 OK; колонки таблицы без утечки аннотации.

# Блок 1: characterization-тесты (гарды до рефакторинга)

Цель: зафиксировать текущее поведение до выноса логики в сервисы.
Принцип: тесты описывают ФАКТ, не идеал (включая баги — с пометкой BUG).

## Фазы
- [x] F0: план + инфра (PYTHONUTF8, запуск существующих)
- [x] F1: ProjectTDL гарды (фильтры, bulk, clone, settings, export) — 16/16 OK
  (`ProjectTDL/Tests/test_guards_f1.py`)
- [x] F2: email_ui гарды (тройник отправки, bulk, фильтры) — 11/11 OK
  (`email_ui/tests_guards_f2.py`)
- [x] F3: ProjectContract гарды (даты, rollup N+1, cashflow) — 9/9 OK
  (`ProjectContract/tests_guards_f3.py`)
- [x] F4: DocRegistry гарды (pdf без шрифтов, import dry-run) — 7/7 OK
  (`DocRegistry/tests_guards_f4.py`)
- [x] F5: инфра (requirements.txt минимум, фикс print в миграции 0010)

## Решения
- Новые тесты: рядом с существующими (`ProjectTDL/Tests/test_guards_*.py`, `email_ui/tests_guards_*.py`?) — не трогать старые файлы.
- Баги фиксируем тестом с маркером `# BUG:` + xfail или assert-факт (не чиним в этом блоке).
- N+1: assertNumQueries до/после.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Блок 16: запушил битый F3 (loader error) — коммит до прогона | 1 | Правило: СНАЧАЛА прогон, потом коммит. Фикс + push 2e6a9dd |
| Правки «удалить пустую строку» через edit склеивают class/def | 2 | Никогда так не делать; только append/replace блоками |
| Блок 2: — | — | 54/54 с первого прогона |
| F1: 2 узла вместо 3 в фикстуре | 1 | assertNumQueries 6->4, count 3->2 |
| F1: Content-Disposition целиком RFC2047 | 2 | decode_header перед assert |
| F2: IntegrityError Emails_email.category_id=1 | 1 | RefMixin: Category/Status pk=1 (как CategoryMixin) |
| F2: assert вне TemporaryDirectory | 1 | asserts внутрь with-блока |
| F2: полное email_ui 1 FAIL filter_panel | — | pre-existing, не моё (файлы только добавлены) |
| F3: UNIQUE payment,task в bulk-тесте | 1 | два разных платежа в bulk_create |
| F4: патч registerFont ломает build PDF | 1 | точечный патч TTFont |
| F5: только Requirements, без проверки | — | проверено прогоном без PYTHONUTF8: OK |
