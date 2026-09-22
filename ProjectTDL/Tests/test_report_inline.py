"""Отчёт master-detail по заданию _Docs/ReportTask.md.

Проверяем:
- детали раскрываются строкой под строкой таблицы (inline-механизм), а не
  прокруткой вниз; старого scrollIntoView к блокам деталей больше нет;
- автопросрочка: срок < даты отчёта и статус не завершён → «Просрочено»
  с подписью «просрочено на N дней»; сегодня / скоро / без срока;
- завершённая задача с прошедшим сроком просроченной не считается;
- длинная история сроков (>5) сворачивается под кнопку «Показать все N»;
- склонение «день/дня/дней» и счётчики статистики.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from ProjectTDL.models import TaskDueDateHistory, TaskNode
from ProjectTDL.reports import ReportGenerator, _days_word
from StaticData.models import Category, ProjectSite, Status


class ReportInlineTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='report_user', password='pw')
        cls.site = ProjectSite.objects.create(name='Объект-отчёт')
        # TaskNode.status/category — FK с default=1: справочные строки pk=1 обязательны.
        cls.open = Status.objects.create(pk=1, name='Открыто')
        cls.done = Status.objects.create(name='Выполнена')
        cls.category = Category.objects.create(pk=1, name='Проектная')
        today = date.today()
        cls.overdue = TaskNode.objects.create(
            owner=cls.user, project_site=cls.site, name='Просроченная',
            status=cls.open, category=cls.category,
            due_date=today - timedelta(days=35))
        cls.closed_past = TaskNode.objects.create(
            owner=cls.user, project_site=cls.site, name='Закрытая в прошлом',
            status=cls.done, category=cls.category,
            due_date=today - timedelta(days=10))
        cls.today_task = TaskNode.objects.create(
            owner=cls.user, project_site=cls.site, name='Срок сегодня',
            status=cls.open, category=cls.category, due_date=today)
        cls.soon_task = TaskNode.objects.create(
            owner=cls.user, project_site=cls.site, name='Срок скоро',
            status=cls.open, category=cls.category,
            due_date=today + timedelta(days=2))
        cls.no_due = TaskNode.objects.create(
            owner=cls.user, project_site=cls.site, name='Без срока',
            status=cls.open, category=cls.category, due_date=None)
        for _ in range(7):
            TaskDueDateHistory.objects.create(task_node=cls.overdue, changed_by=cls.user)

    def _html(self):
        return ReportGenerator.generate_html_report(TaskNode.objects.all())

    def test_overdue_overrides_open_status(self):
        html = self._html()
        self.assertIn('Просрочено', html)
        self.assertIn('status-overdue', html)
        self.assertIn('просрочено на 35 дней', html)

    def test_closed_past_due_not_overdue(self):
        info = ReportGenerator._task_info(TaskNode.objects.get(pk=self.closed_past.pk))
        self.assertEqual(info['status'], 'Выполнена')
        self.assertEqual(info['status_class'], 'completed')
        self.assertNotEqual(info['due_class'], 'deadline-overdue')

    def test_today_soon_nodate_labels(self):
        today_info = ReportGenerator._task_info(TaskNode.objects.get(pk=self.today_task.pk))
        self.assertEqual(today_info['due_label'], 'сегодня')
        self.assertEqual(today_info['due_class'], 'deadline-today')
        soon_info = ReportGenerator._task_info(TaskNode.objects.get(pk=self.soon_task.pk))
        self.assertEqual(soon_info['due_label'], 'через 2 дня')
        self.assertEqual(soon_info['due_class'], 'deadline-soon')
        nodate_info = ReportGenerator._task_info(TaskNode.objects.get(pk=self.no_due.pk))
        self.assertEqual(nodate_info['due_label'], 'без срока')
        self.assertEqual(nodate_info['due_class'], 'deadline-empty')

    def test_inline_mechanism_present_no_scroll_down(self):
        html = self._html()
        # Строки сводной таблицы и блоки деталей на месте для переноса в inline-row.
        self.assertIn('summary-row-', html)
        self.assertIn('task-details-', html)
        self.assertIn('initInlineTaskDetails', html)
        self.assertIn('toggleInlineTaskDetails(', html)
        self.assertIn('inline-row-', html)
        self.assertIn('detailsSectionTitle', html)
        # Кнопка «Детали / Свернуть», старого «Подробнее» и прыжка вниз больше нет.
        self.assertIn('details-toggle', html)
        self.assertNotIn('Подробнее', html)
        self.assertNotIn("task-details-' + taskId).scrollIntoView", html)

    def test_history_truncated_after_five(self):
        html = self._html()
        self.assertIn(f'history-extra-{self.overdue.pk}', html)
        self.assertIn('Показать все 7 изменений', html)

    def test_days_word_declension(self):
        self.assertEqual(_days_word(1), 'день')
        self.assertEqual(_days_word(2), 'дня')
        self.assertEqual(_days_word(5), 'дней')
        self.assertEqual(_days_word(11), 'дней')
        self.assertEqual(_days_word(21), 'день')
        self.assertEqual(_days_word(35), 'дней')

    def test_stats_counts(self):
        html = self._html()
        # Хвосты «Итоговый отчет» / «Итоги по сводной таблице» удалены —
        # вся статистика только в верхней карточке-метрике.
        self.assertNotIn('Итоговый отчет', html)
        self.assertNotIn('Итоги по сводной таблице', html)
        self.assertNotIn('Распределение по статусам', html)
        # Верхняя карточка: базовые метрики + распределение по статусам.
        for label in ('Всего задач', 'Общая стоимость', 'Всего подзадач',
                      'Изменений сроков', 'Активные', 'Завершенные',
                      'Просрочено', 'Без срока'):
            self.assertIn(label, html)


class ReportStage34Test(TestCase):
    """Этапы 3–4: поиск, фильтры, сортировка, пагинация, состояние, экспорт."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='report34_user', password='pw')
        cls.site = ProjectSite.objects.create(name='Объект-этапы')
        cls.open = Status.objects.create(pk=1, name='Открыто')
        cls.category = Category.objects.create(pk=1, name='Проектная')
        today = date.today()
        cls.overdue = TaskNode.objects.create(
            owner=cls.user, project_site=cls.site, name='Просроченная задача',
            status=cls.open, category=cls.category,
            due_date=today - timedelta(days=35))
        cls.nodate = TaskNode.objects.create(
            owner=cls.user, project_site=cls.site, name='Без срока задача',
            status=cls.open, category=cls.category, due_date=None)

    def _html(self):
        return ReportGenerator.generate_html_report(TaskNode.objects.all())

    def test_data_attributes_for_filters(self):
        html = self._html()
        # Поисковый blob: имя задачи в нижнем регистре.
        self.assertIn('просроченная задача', html)
        self.assertIn('data-search=', html)
        # Фильтр и порядок срока: просрочка — отрицательный ключ, без срока — большой.
        self.assertIn('data-due="overdue"', html)
        self.assertIn('data-due-order="-35"', html)
        self.assertIn('data-due="nodate"', html)
        self.assertIn('data-due-order="1000000000"', html)
        self.assertIn('data-subtask-count=', html)
        self.assertIn('data-history-count=', html)

    def test_filter_options_rendered(self):
        html = self._html()
        for select_id in ('filter-contractor', 'filter-status', 'filter-building',
                          'filter-chapter', 'filter-due', 'page-size'):
            self.assertIn(f'id="{select_id}"', html)
        # Статусы из данных: «Открыто» и вычисленное «Просрочено».
        self.assertIn('>Открыто<', html)
        self.assertIn('>Просрочено<', html)
        self.assertIn('<option value="overdue">Просроченные</option>', html)
        self.assertIn('<option value="__none">Без ответственного</option>', html)

    def test_toolbar_chips_and_pager(self):
        html = self._html()
        self.assertIn('id="report-search"', html)
        for chip in ('all', 'overdue', 'nodate', 'noresp', 'subtasks', 'history'):
            self.assertIn(f'data-chip="{chip}"', html)
        self.assertIn('id="filter-counter"', html)
        self.assertIn('id="report-pager"', html)
        self.assertIn('reportGotoPage(', html)

    def test_sortable_headers(self):
        html = self._html()
        for key in ('id', 'name', 'status', 'contractor', 'due', 'price', 'subtasks', 'history'):
            self.assertIn(f'data-sort-key="{key}"', html)
        # Сортировка по сроку по умолчанию — сначала просроченные.
        self.assertIn("sortKey: 'due'", html)

    def test_state_export_print_functions(self):
        html = self._html()
        for fn in ('sortSummaryBy(', 'applyReportView(', 'saveReportState(',
                   'loadReportState(', 'reportGetOpenIds(', 'reportOpenChanged(',
                   'reportOpenFromUrl(', 'reportRestoreOpen(', 'exportReportCsv(',
                   'printReportWithDetails(', 'initReportView(', 'resetReportFilters('):
            self.assertIn(fn, html)
        self.assertIn('afterprint', html)
        self.assertIn('taskReportV1', html)
        # Кнопки печати с деталями и экспорта в шапке.
        self.assertIn('printReportWithDetails()', html)
        self.assertIn('exportReportCsv()', html)
        self.assertIn('.csv', html)
