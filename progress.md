# progress — Блок 1

## 2026-10-06
- F0: план создан. Baseline ProjectTDL: 37/37 OK.
- F1 done: `ProjectTDL/Tests/test_guards_f1.py`, 16/16 OK (3 прогона, 2 фикса моих тестов).
  Подтверждены баги: SubTaskCloneView без referer -> ValueError; price с запятой
  в update_task_field -> error (bulk запятую ест); чужую задачу правит любой;
  bulk не пишет TaskDueDateHistory. N+1: 2 узла = 4 запроса render/row_attrs.
- F3 done: `ProjectContract/tests_guards_f3.py`, 9/9 OK.
  Ручной due священен, каскад до внуков, цикл родителей завершается,
  ДДС идемпотентен, rollup=1 запрос, bulk_create обходит clean (переплата 1200>1000).
- F4 done: `DocRegistry/tests_guards_f4.py`, 7/7 OK.
  Helvetica-фолбэк собирается в PDF; K1 dry-run без accdb -> CommandError;
  DesignBase на закрытом порту -> DesignBaseUnreachable.
- F5 done: `requirements.txt` (минимум, пины из pip freeze), фикс print '->'
  в миграции 0010 (прогон без PYTHONUTF8: OK).
- ФИНАЛ: ProjectTDL+ProjectContract+DocRegistry — 226/226 OK (61.6s).
- Блок 2 done: N+1 в TaskNodeTable убит (EXISTS-аннотация, 0 запросов на
  рендер строк вместо 2/строку). ProjectTDL 54/54 OK с первого прогона.
- Блок 3 done: тройник отправки -> compose_service. 33/33 целевых OK,
  полный email_ui 255 — только pre-existing filter_panel. Поведение 1:1.
- Блок 4 done: фильтры + bulk ProjectTDL -> services. ProjectTDL 69/69 OK
  с первого прогона. Поведение 1:1, обёртки в views сохранены.
- Блок 5 done: админка задач -> services (push 28c8453). TestNodeAdmin
  79/79 OK. save_model: silent except -> warning в лог.
- Блок 6 done: reports гигиена + гарды (push aff52ff). ProjectTDL 89/89 OK.
  Полный email_ui: 251 тест, 1 падение — FilterParamsRobustnessTest.
  test_filter_panel_opens_when_filters_active: PRE-EXISTING (падает и отдельно,
  мои файлы только добавлены, tests.py/templates не тронуты).
  Находки F2: send ест ';'; вложения без link теряются молча (file_path '');
  copy/export пишут через E_MAIL_DIRECTORY (патчится как атрибут views).
- Блок 25 done: чистые хелперы email_ui/views.py -> services/query_service.py + services/navigation.py (views 2806->2525, тела 1:1, re-export). Тесты tests_views_b25 36/36; полный email_ui 317/317 OK (235s).
- Блок 27 done (B1): compose-поток views->services/compose_flow (views 2525->2395, тела 1:1, re-export). Тесты tests_compose_b27 20/20; полный email_ui 340/340 OK (231s).
- Блок 28 done (B2): thread-хелперы views->services/thread_service (views 2395->2289, тела 1:1, re-export). Тесты tests_threads_b28 6/6; полный email_ui 346/346 OK (226s).
- Блок 29 done (B7): фазы custom_task_view views->services/task_view (views 965->834, тела 1:1; filter_tasks_ajax тоже на фазе 3). Тесты test_task_view_b29 12/12; ProjectTDL 124/124 OK, check clean.
- Блок 30 done (B6+B8): Seen-синхронизация views->services/seen_sync + push_seen_async в daemon-потоке (5 точек вызова); гард tests_filter_fanout_b30 (tags+attachments без дублей). Тесты tests_seen_b30 5/5; полный email_ui 351/351 OK (247s).
- Блок 31 done (B4): 7 modal create/edit -> _save_modal_form (views, без магии фабрик; contact_create с 2 формами оставлен). Полный email_ui 353/353 OK (245s).
- ФИНАЛ B1-B8: полный прогон всех приложений 689/689 OK (333s). Все 8 предложений закрыты, каждый блок запушен.
