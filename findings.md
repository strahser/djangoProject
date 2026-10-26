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

## Чистка 2026-10-14 (быстрые правки, вердикт владельца)
- `.env` грузится ТЕПЕРЬ В НАЧАЛЕ settings (раньше в конце): override
  `DJANGO_MEDIA_ROOT`/`DJANGO_DEBUG`/`DJANGO_ALLOWED_HOSTS` реально работают
  (был латентный баг — десяток настроек читалось до загрузки .env).
- `.env` (машинно-локальный): добавлен `DJANGO_MEDIA_ROOT=d:\Автоматизация\djangoProjectDB\media`
  — 3 теста ProjectContract упали из-за отсутствия `e:\`, теперь зелёные.
- requirements.txt: + `pymupdf` (только тесты DocRegistry) — 7 ошибок устранены.
- Удалены мёртвые URL `/demo`, `/popovers` (шаблоны bootstrap_base/bootstrap_popovers
  не существуют — открывались в 500).
- Удалено: дампы парсера в корне (2 txt, 110 КБ), `db.sqlite3` 0 байт в корне,
  `.playwright-mcp/` (логи браузера), `services/tests_py_projects.py` (демо
  python-gantt 2015 года с print).
- `auth_telegram.py` из корня → `scripts/auth_telegram.py` (путь к BASE_DIR
  пересчитан на parent.parent).
- БД: снесены сентябрьские бэкапы (−113 МБ: db_bak_20260922 + 4 personal_db_bak),
  свежий db_bak_20261007_DS13 оставлен. VACUUM db.sqlite3: 187 → 110 МБ.
- `tests_settings_b9.EnvFlagTest` расширен: posture-тест учитывает
  `DJANGO_MEDIA_ROOT` override.
- Итог: 768/768 OK (было 10 ошибок, все окруженческие).

## P2 (2026-10-14, продолжено)
- `rule_run_now`: был синхронный `process_emails(Email.objects.all())`
  в HTTP-запросе (таймаут на реальной базе). Новый `services/rule_runner.py`:
  `run_rule_over_all` + `run_rule_async` в daemon-потоке (паттерн B6/seend_sync),
  итог — в EmailAutomationLog + logs/email_ui.log. Вьюха возвращает 204 сразу.
- Телеграм-парсер: `_log` через print в views/scheduled/parser → loguru
  (logs/telegram_parser.log), консоль runserver чистая.
- `services/DataFrameRender/RenderDfFromModel.py`: 2× `print(e)` →
  `logger.exception` (молча глотались фильтры DataFrame).
- Декомпозиция `email_ui/views.py` 2055 → ~1830 строк: новые `views_contacts.py`
  (контакты/группы/теги), `views_filters.py` (сохранённые фильтры),
  `views_rules.py` (правила), `services/modal_forms.py` (`_save_modal_form`→
  `save_modal_form`), urls.py переключены (url-имена те же).
  Чистка импортов views: −17 (формы/модели/хелперы переехавших сегментов).
  НЕ тронуты намеренные ре-экспорты для тестов: query_service/thread_service
  хелперы + `ALLOWED_SORT_FIELDS`/`_safe_next` (контракт блока 25, гард в
  tests_views_b25:276) — первая чистка их снесла, тесты поймали, вернул.
- Косяк сплита: `views_filters.py` без `redirect` (NameError в 2 тестах) —
  поймано прогоном, исправлено.
- `email_ui/utils.py` 1041 → ~775 строк: адресный блок (758–1041, 284 строки:
  транслит/поиск контактов, extract_*, resolve_sender_to_email,
  canonical_* , аватары) → новый `email_ui/address_utils.py` 1:1 скриптом
  (якоря + бэкап, `import hashlib` из середины — в шапку). utils.py оставил
  ре-экспорт 9 имён (включая приватный `_EMAIL_STANDALONE_RE` — его тянет
  compose_flow) — все ~15 мест импорта работают без правок.
  Первая попытка скрипта упала на off-by-one в ассёрте (две пустые строки
  перед блоком) — поймано проверкой, не записями.

## ProjectContract (2026-10-14, продолжено)
- `admin.py` 749 → ~540 строк: фильтры (блок 29–109 + миксин/каскады 484–615,
  217 строк) → новый `admin_filters.py` 1:1 скриптом. Убраны дубль-импорт
  моделей (строка 12) и уехавший `gettext_lazy`. ContractAdmin/
  EstimateConceptAdmin остались — контракты тестов целы.
- `views.py` 619 → ~160 строк (только карточка: detail/tab/reminders/files):
  `views_cashflow.py` (дашборд/памятка/cashflow), `views_dds.py` (ДДС+акты+xlsx),
  `views_payments.py` (тогглы/гант/экспорт/CRUD), urls.py переключён (имена те же).
  Мёртвые импорты `logger`/`csrf_exempt` (0 использований) выкинуты.
  `_build_cashflow_chart` — ре-экспорт из views (тест tests.py:675).
- Косяки сплита (оба пойманы, не записями): декораторы следующей функции
  уходили в хвост предыдущего чанка (дубль) — починен сплиттер + перезапуск
  из бэкапа (ассёрт порядка чанков спас от повторной резки уже резанного файла);
  забыт `JsonResponse` в views_payments (2 NameError) — добавлен.
- `email_ui/models.py` 518 → ~165 строк: `models_tags.py` (EmailTag,
  EmailEmailTag), `models_contacts.py` (Contact/ContactEmail/ContactGroup/
  EmailAlias), `models_templates.py` (EmailTemplate+Variable),
  `models_automation.py` (EmailRule/AutomationLog). models.py — ре-экспорт
  10 имён (миграции не меняются: app_label+имя те же, --check чист).
  Косяков не было: якоря чинились дважды до записи (голый `class X` без
  скобок; shared-границы блоков), записи только после зелёных ассёртов.
- Итог: 770/770 OK.
- Итог: 770/770 OK (+2 новых RuleRunnerTest: sync-прогон с логом/меткой,
  async-поток по паттерну tests_seen_b30 с моком ядра — замок TestCase).

## Реестр М1/К1 в Excel + чистка экшенов (2026-10-15)
- Экшены adminactions: убраны экспорты выборки (csv/xls/fixture) и merge —
  через exclude в add_to_site (urls.py), пакет не патчился.
- Новый DocRegistry/exports.py (build_registry_xlsx: титул, жирная шапка
  с заливкой, зебра, границы, автофильтр, freeze A3, ширины, даты как даты)
  + экшен export_registry_xlsx в _EntryAdminBase (М1 и К1, все сайты).
  Колонки: Код | Наименование здания | Раздел | Номер здания |
  Имя эл. файла | Разраб. | Дата подачи. +4 теста.
  Косяк: edit вставил класс в середину чужого теста (oldString совпал
  внутри метода) — починено скриптом (хвост test_admin_panels_separated
  и test_main_admin_index_grouped возвращены), швы проверены чтением.
- Итог: 774/774 OK.

## Реестр М1/К1: пагинация, полный экспорт, per-page (2026-10-15)
- _EntryAdminBase: list_per_page=50, list_max_show_all=100000 (галочка в шапке
  таблицы выделяет ВСЮ выборку по фильтрам — select_across из коробки),
  show_full_result_count=True.
- Новый экшен export_all_filtered: выгрузка ВСЕЙ выборки по текущим
  фильтрам/поиску, игнорируя выделение и пагинацию (get_changelist_instance).
  Имя файла reestr_M1_ALL_...xlsx. Старый export_registry_xlsx (по выделению)
  оставлен — работает и с select_across.
- Селектор «записей на страницу» (25/50/100/all) в тулбаре чейнджлиста:
  cookie registry_per_page (GET-параметр нельзя — Django трактует неизвестные
  ключи как lookup-фильтр и шлёт ?e=1; Paginator не принимает per_page=0,
  «all» = лимит 100000). Шаблон templates/jazzmin/admin/DocRegistry/change_list.html.
- Косяки по пути (все пойманы тестами): session-подход не работал в тестах
  (self.client.session не сохранялся между запросами) → переделано на cookie;
  забытые импорты HttpResponseRedirect/M1EntryAdmin/get_user_model; синглтон
  ModelAdmin протекал list_per_page между запросами → сброс в начале changelist_view.
- Итог: 777/777 OK (+3 новых теста).

## Задачи из позиций сметы с группировкой (2026-10-15)
- Экшен create_tasks_from_concepts: создаются только позиции без акта И без
  задач (раньше повтор плодил вторую связку). На каждый договор — родительская
  суммарная задача «<Договор> — работы по смете» (переиспользуется), позиции —
  дочерние subtask'и; цена родителя = сумме позиций под ним (self-healing).
- task_mutations: create_task_with_defaults принял parent/node_type (MPTT-вставка
  за 1 save; присваивание parent + save() дерево не двигает) + новый
  get_or_create_contract_summary / summary_task_name.
- Страница подтверждения: колонка «Родитель», бейджи пропуск (акт/есть
  задачи/нет договора), get_item уже был в admin_totals.
- Тесты: обновлены (родитель/цена/skip повтора) + новые (2 договора — 2 родителя,
  переиспользование родителя, метка «есть задачи»). Косяк: ET/ЕТ в именах.
- Итог: 780/780 OK (+3 новых теста).

## Drag-and-drop дерева задач (2026-10-15)
- Страница /: ручка-грип в первой ячейке каждой строки; drop на строку —
  сделать дочерней (subtask), drop на синюю зону над таблицей — открепить
  в корень (самостоятельная, node_type='task'). Плюс пункт контекстного меню
  «Открепить (в корень)». После успеха — reload (паттерн страницы).
- Бэкенд: POST task/move/ (task_move, права как в update_task_field —
  только владелец), сервис move_task в task_mutations: циклы запрещены
  (сам в себя / в потомка), attach через mptt move_to, detach через
  save + objects.rebuild() (прямое присваивание parent дерево не двигает).
- Ручки переживают перерисовки: initDragHandles() вызывается из initTreeView()
  (все 3 места), плюс контекстное меню не тронуто.
- Тесты: ProjectTDL/Tests/test_task_move.py, 9 шт. (сервис + вьюха: detach,
  attach, циклы, чужой, 404). Косяк: stale MPTT-объект в ассёрте детей —
  лечится refresh_from_db.
- Итог: 790/790 OK (+9 новых тестов).

## MS Project: повысить/понизить уровень + фикс DnD (2026-10-15)
- Баг «некорректный id задачи»: нативный DnD текста/ссылок внутри строки
  ронял мусор в drop-зону — теперь числовая защита /^\d+\$/ в обоих
  drop-хендлерах и в postTaskMove (молча игнор, без POST).
- Кнопки Понизить/Повысить в панели действий (только одиночный выбор) +
  пункты контекстного меню: indent (дочерняя предыдущего соседа),
  outdent (на уровень родителя; дочь корня — в корень).
- Бэкенд: task_move принял mode=attach/detach/indent/outdent; сервис
  indent_task/outdent_task поверх общего _do_move (выделен из move_task).
- Тесты: +7 (сервис indent/outdent/границы + режимы вьюхи). Рендер / — 200.
- Итог: ProjectTDL 144/144 OK.

## Скрипт папки по дате: внутренние команды TC (2026-10-21)
- Задача: кнопка в панели TC создаёт папку 2026_10_21_ В АКТИВНОЙ панели и
  включает режим переименования (Shift+F6) для дописывания суффикса.
- Отвергнуто: TOTALCMD.EXE /O - ключ открывает путь в ДРУГОЙ панели TC
  («проваливается» не туда); SendInput с F7 - клавиши уходят в окно на
  переднем плане, ненадёжно; AHK-скрипт (Habr, 2009) - нужен AutoHotkey.
- Принято: внутренние команды TC сообщением WM_USER+1075 в окно класса
  TTOTAL_CMD (механизм wiki TC «AutoHotkey: Send a command to TC»):
  cm_MkDir(907) -> поле ввода имени -> WM_SETTEXT + Enter -> cm_RenameOnly(1002)
  -> инлайн-редактор -> End (SendInput) ставит каретку в конец имени.
- Нюансы, найденные при отладке:
  * SendMessage с cm_MkDir БЛОКИРУЕТ вызывающий процесс (TC ждёт закрытия
    модального диалога) - только PostMessage;
  * cm_CopySrcPathToClip (2029) даёт путь активной панели, но портит буфер -
    старое содержимое сохраняем и восстанавливаем;
  * инлайн-редактор TC - «фейковый» HWND (HwndlessEditor*), нового окна не
    создаёт, видимость всегда False; признак открытого редактора - фокус в
    потоке TC (GetGUIThreadInfo);
  * переименование требует, чтобы TC был в фокусе, и паузу ~1.2 с после
    создания папки (иначе команда приходит раньше обновления панели);
  * запуск через python.exe перехватывает фокус консолью - кнопка должна
    запускать pythonw.exe.
- Файлы: scripts/create_dated_folder.py, scripts/Tests/test_create_dated_folder.py
  (8 тестов: имя папки, запасной путь без TC, сверка номеров команд с
  TOTALCMD.INC), scripts/README.md, кнопка cmd27/param27 в default.bar.
- Итог: 8/8 тестов скрипта OK; полный прогон проекта - 778/778 OK.

## Скрипт папки по дате: ускорение и режим «вставь дату и выйди» (2026-10-21)
- Замеры прежней версии: цикл «создать папку -> переименование» занимал
  ~3 с и шёл в несколько «дёрганий» (буфер обмена + две фиксированные
  паузы 1.2 с и 0.9 с + опрос по 150 мс).
- Что убрано:
  * запрос пути активной панели (cm_CopySrcPathToClip) из рабочего сценария —
    он портит буфер обмена и стоил ~0.5 с; путь пишется в лог только при
    неудаче;
  * фиксированные паузы 1.2 с / 0.9 с — вместо них ожидание конкретных
    событий с шагом 20-60 мс;
  * SendInput(End) — каретка ставится сообщением EM_SETSEL прямо в поле.
- Открытие: поле переименования в TC 11 - это обычный edit-контрол класса
  TInEdit (получает фокус), а не «фейковое» окно HwndlessEditor*; имя в нём
  читается через WM_GETTEXT. Это дало и быструю проверку (открыто ли нужное
  имя — если нет, переименование отменяется через ESC), и EM_SETSEL.
- Новая логика: cm_RenameOnly повторяется каждые 60 мс, пока редактор не
  откроется (команда безопасна — имя не меняется). Если открылся не тот
  файл - ESC, ничего не переименовано.
- НОВЫЙ РЕЖИМ ПО УМОЛЧАНИЮ (по просьбе пользователя): скрипт только
  открывает окно ввода имени (как F7) и вписывает дату, дальше Enter и
  Shift+F6 пользователь жмёт сам. Полный автомат - под флагом --auto.
- Итог: быстрый режим ~0.2 с (окно ввода с датой), --auto ~0.5 с
  (папка создана + переименование открыто + каретка в конце имени).
- Тесты: scripts/Tests/test_create_dated_folder.py - 10 тестов (добавлены
  проверки режимов по умолчанию и --auto). Полный прогон: 822/822 OK.

## Django: чистый старт без ошибки IMAP, чистка .bat (2026-10-21)
- Жалоба: «Django вызывает ошибку запуск» + огромный traceback IMAP.
  Разбор: сервер как таковой запускался нормально; ошибку ронял
  фоновой APScheduler-процесс (fetch_new_emails_job, next_run_time=now):
  Яндекс ответил «[UNAVAILABLE] LOGIN internal server error» (их временная
  внутренняя ошибка - позже вход заработал снова: 4651 писем в INBOX,
  2062 в «Отправленные», ошибок 0).
- Почему был traceback: MailboxLoginError из imap_tools НЕ входит в
  _CONN_ERRORS (там только imaplib/ConnectionError/TimeoutError/OSError),
  поэтому ошибка входа уходила в общий except -> logger.exception.
- Исправлено (Emails/ЕmailParser/ParsingImapEmailToDB.py):
  * отдельная ветка MailboxLoginError -> warning без traceback;
  * _is_transient_login_error: «UNAVAILABLE / INTERNAL SERVER ERROR» ->
    повтор входа с паузой; «AUTHENTICATIONFAILED» -> без повторов, с
    подсказкой про пароль приложения;
  * в .env добавлен флаг EMAIL_AUTO_FETCH_ENABLED (=1) - при 0 планировщик
    автозагрузки не стартует вообще (settings.EMAIL_AUTO_FETCH_ENABLED,
    email_ui/scheduled.py).
- Плюс убраны warning'и django-import-export: TaskNodeResource объявлял
  поля design_chapter__full_name и price, но не включал их в Meta.fields
  -> поля молча не выгружались. Добавлены в whitelist; колонка полного
  названия названа 'design chapter full', чтобы не было двух одинаковых
  колонок 'design chapter'.
- Удалены лишние .bat запуска сервера: django.bat (активировал несуществующий
  e:\Venvs\... - мёртвый путь) и runserver_local.bat (по просьбе владельца).
  Остался один запуск сервера: serve_waitress.bat (127.0.0.1:8000, waitress).
  Для dev-сервера с автоперезагрузкой:
  .venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
- Тесты: Emails/Tests/test_imap_errors.py - 7 тестов (транзиентность ошибок
  входа, повтор/без повтора, отсутствие traceback, флаг автозагрузки).
  Полный прогон: 829/829 OK.

## Единый launcher сервера + кнопка в панели TC (2026-10-21)
- Убраны лишние .bat запуска сервера: django.bat (мёртвый путь e:\Venvs\...),
  runserver_local.bat (дубль dev-запуска) и serve_waitress.bat (прод-режим
  перенесён в аргумент). Остался ОДИН: start_server.bat.
- start_server.bat:
    start_server.bat                -> dev: 127.0.0.1:8000 (--noreload)
    start_server.bat 8013          -> dev на другом порту
    start_server.bat --waitress    -> прод-режим (waitress, threads=4)
    start_server.bat --waitress 8013
  Dev-режим с --noreload: иначе из-за autoreload поднимаются два
  планировщика почты (APScheduler) и письма качаются дважды.
- Проверено: оба режима поднимают сервер, /healthz/ -> {"status":"ok",
  "db":"ok"}, порт освобождается после остановки.
- «Ссылка» на запуск: кнопка «Django» (слот 28) в панели TC ->
  start_server.bat, рабочая папка = корень проекта. Рядом кнопка
  «Папка по дате» (слот 27, scripts/create_dated_folder.py).
  В панели TC файл default.bar в кодировке CP1251, переводы строк
  смешанные (CRLF/LF) - правка делается по байтам с regex-разбором.
- Важно: слот 27 панели изначально был кнопкой запуска сервера
  («runserver_local») - она перепрофилирована под скрипт папки по дате,
  поэтому кнопка сервера добавлена новым слотом 28.

## Письмо → задача одним действием + чистка пользователей (2026-10-23)
- Кнопка «Создать задачу» в блоке «Задачи письма» вела в админку на полную
  форму TaskNode. Связь письма при этом терялась: TaskNodeAdmin объявлял
  context['email_id']/next_url, но ни один шаблон не выводил скрытые поля
  _email_id/_next, поэтому save_model их не видел.
- Вторая потеря: блок «Задачи письма» читает M2M email.tasks, а создавался
  только EmailTaskLink (отдельная модель) — задача в блоке не появлялась,
  пока письмо не привязывали ещё раз вручную.
- Теперь create_task_from_email (POST; логика вынесена в
  email_ui/services/email_tasks.py и переиспользуется правилами):
  * одно действие: TaskNode + email.tasks.add(task) + EmailTaskLink
    (link_type='created_from', created_by=request.user);
  * название = тема письма (сжатая, обрезка до 150 — max_length TaskNode.name);
  * проект: из письма, иначе активный проект пользователя
    (UserSettings.active_project) — TaskNode.project_site обязателен, а у 7054
    из 7288 писем проект не заполнен;
  * без проекта — понятное сообщение, задача не создаётся;
  * повторный клик/прогон правила не плодит дубли (created_from + название);
  * HTMX: обновлённый partial email_tasks_body + OOB-счётчик «Задачи (N)»
    + showToast; обычный POST — messages + redirect (next).
- UI: единый partial email_ui/partials/email_tasks_body.html используют
  страница письма, модалка в inbox и (кнопкой formaction) страница
  «Прикрепить к задачам». Шаблон create_task_form.html удалён.
- detach_task теперь чистит и EmailTaskLink — раньше в админском inline
  письмо оставалось привязанным после отвязки.
- Действие правила create_task (было объявлено в ACTION_TYPES, но не
  выполнялось — «Unknown action») реализовано: владелец из owner_id, иначе
  первый активный суперпользователь; проект из project_id, иначе проект
  письма/активный проект владельца. Повторный прогон дубль не создаёт.
- Админка (ProjectTDL/admin.py): formfield_for_foreignkey для owner отдаёт
  только суперпользователей (в базе это ssg) + владелец по умолчанию —
  текущий пользователь; save_model дополнительно пишет email.tasks.add;
  добавлен templates/admin/ProjectTDL/tasknode/change_form.html со скрытыми
  _email_id/_next.
- Пользователи: удалены тестовые tmpcheck, tmpcheck2 (ссылок на них не было).
  Остались ssg (суперпользователь) и docagent — сервисная учётка с действующим
  API-токеном DocRegistry (M1 DOC-3, команда docs_agent_token); в списке
  владельцев задач она не появляется.
- Попутно: scripts/create_dated_folder.py — запасной путь (TC не запущен)
  игнорировал --name и создавал папку с текущей датой. Теперь имя совпадает
  с тем, что скрипт вставил бы в TC. Тест на это падал только не 21-го числа
  (был привязан к дате).
- Тесты: email_ui/tests_email_task_b58.py — 17 тестов. Полный прогон:
  846/846 OK.

## Переезд почтового архива e: → d: и разрешение путей (2026-10-26)
- Диск E: недоступен; архив лежит на `d:\Проекты Симрус\Переписка`.
  Внутри два варианта исторической раскладки: `...\Переписка\imap_attachments\...`
  (старая, 5019 писем / 11708 вложений) и
  `...\Переписка\Bitrix 24\imap_attachments\...` (1446 / 2007), плюс
  `...\Переписка\2024-06-26_архив` (585 писем) и файлы `M1` (34).
  Новые письма уже пишутся в `E_MAIL_DIRECTORY` из `.env`
  (`d:\Проекты Симрус\Переписка\Bitrix 24`) — код сохранения не меняли.
- `Emails/paths.py`: единая точка чтения устаревших путей.
  `resolve_email_path` сначала возвращает существующий путь, затем пробует
  тот же относительный путь на диске `E_MAIL_DIRECTORY` (переименование
  диска), затем перебазирует хвост от `imap_attachments`/`sent`/`drafts`
  на текущий корень или его родителя. Это покрывает обе раскладки, архив
  2024 и `M1`.
- Модели: `Email.resolved_link`, `Email.get_html_file_path`,
  `Attachment.resolved_path`, `file_path_js`, `file_url`, `folder_path`.
  Читающие места переведены на них: email_ui/views.py, utils.py,
  email_sender.py, export_service.py, file_text.py, compose_service.py,
  compose_flow.py, Emails/admin.py, populate_attachments.py,
  DocRegistry/api.py, шаблоны вложений.
- Команда `rewrite_email_paths` (dry-run по умолчанию, `--apply`):
  * без `--old` сначала определяет смену диска (все пути архива на одном
    чужом диске) и меняет только букву `e:` → `d:`, сохраняя любые
    подкаталоги;
  * иначе ищет единственный старый корень по маркерам архива;
  * `--old`/`--new` позволяют задать замену вручную.
- Бэкап перед правкой: `djangoProjectDB\db_bak_20261026_paths.sqlite3`
  (integrity ok, 7295 писем, 13858 вложений).
- Фактически в БД: 20801 замена `e:\` → `d:\` (7050 Email.link +
  13751 Attachment.file_path), затем 63 точечные замены
  `C:\Bitrix 24\...` → `d:\...\Bitrix 24\...` (все папки существуют).
  Итог: `e:` и `C:\Bitrix 24` — 0; все Email.link и Attachment.file_path
  на `d:`. Остались только 3 тестовых письма `media_mail` и 4 отсутствующих
  файла (удалены/не созданы до миграции).
- Попутно убраны жёсткие `e:`: fallback `MEDIA_ROOT` и `E_MAIL_DIRECTORY`
  в settings.py, корень `/media/` в urls.py теперь
  `os.path.dirname(E_MAIL_DIRECTORY)`.
- Тесты: `Emails/Tests/test_paths_b59.py` — 15 тестов (резолвер, свойства
  моделей, dry-run/apply, идемпотентность, автоопределение диска,
  пути без маркеров). Полный прогон: 861/861 OK (420 с).
