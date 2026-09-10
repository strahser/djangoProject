from django.db import models


class DocRegisterEntry(models.Model):
    """Строка реестра РД — зеркало [01 Реестр] М1.accdb (канон §3).

    Маппинг колонок accdb 1:1 (исходные имена — в help_text).
    История — цепочкой DocRevision, старые строки не правятся.
    """

    code = models.PositiveIntegerField(unique=True, verbose_name='Код', help_text='accdb: код')
    section = models.CharField(max_length=20, blank=True, default='', verbose_name='Раздел', help_text='accdb: раздел (код из [Разделы])')
    building_no = models.CharField(max_length=20, blank=True, default='', verbose_name='Номер здания', help_text='accdb: Номер здания')
    cipher = models.CharField(max_length=200, blank=True, default='', db_index=True, verbose_name='Шифр', help_text='accdb: шифр')
    file_name = models.CharField(max_length=1000, blank=True, default='', verbose_name='Имя эл. файла', help_text='accdb: Назв Эл файла (max 771 в live)')
    approval_status = models.CharField(max_length=50, blank=True, default='', verbose_name='Согласование', help_text='accdb: согласование')
    approval_date = models.DateField(null=True, blank=True, verbose_name='Дата согласования', help_text='accdb: дата согласования')
    submitted_flag = models.CharField(max_length=10, blank=True, default='', verbose_name='Подано', help_text='accdb: подано на согласование')
    change_descr = models.TextField(blank=True, default='', verbose_name='Описание изменений', help_text='accdb: Описание изм')
    building_name = models.CharField(max_length=300, blank=True, default='', verbose_name='Здание', help_text='accdb: Наименование здания')
    submit_date = models.DateField(null=True, blank=True, verbose_name='Дата подачи', help_text='accdb: Дата подачи на согласование')
    acts = models.CharField(max_length=500, blank=True, default='', verbose_name='Акты', help_text='accdb: Акты (max 289 в live)')
    contractor_new = models.CharField(max_length=20, blank=True, default='', verbose_name='Разраб. нов.', help_text='accdb: разраб_нов')
    contract = models.ForeignKey(
        'ProjectContract.Contract', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='doc_entries',
        verbose_name='Договор',
    )
    accdb_row_hash = models.CharField(
        max_length=64, blank=True, default='',
        verbose_name='Хеш строки accdb',
        help_text='sha1 конкатенации полей — для ночного check_accdb_drift (DOC-5)',
    )

    def __str__(self):
        return f'{self.code}: {self.cipher or self.file_name}'[:120]

    class Meta:
        verbose_name = 'Запись реестра РД'
        verbose_name_plural = 'Реестр РД'
        ordering = ['code']


class DocRevision(models.Model):
    """Файл ревизии документации — шаг 1–2 конвейера (канон §2)."""

    SOURCE_CHOICES = [
        ('email', 'Из письма'),
        ('yadi', 'Yandex.Disk ссылка'),
        ('manual', 'Вручную'),
    ]
    STATUS_CHOICES = [
        ('received', 'Получена'),
        ('validating', 'На проверке'),
        ('checked_ok', 'Проверена'),
        ('has_remarks', 'Замечания'),
        ('registered', 'В реестре'),
        ('issued', 'Выдана в ПР'),
    ]

    entry = models.ForeignKey(
        DocRegisterEntry, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='revisions', verbose_name='Запись реестра',
        help_text='Пусто до шага 3 (register) — приём идёт раньше привязки к реестру',
    )
    rev_no = models.PositiveIntegerField(default=1, verbose_name='№ ревизии')
    file = models.FileField(
        upload_to='DocRegistry/incoming/%Y/%m/', null=True, blank=True,
        verbose_name='Файл ревизии',
    )
    sha256 = models.CharField(max_length=64, blank=True, default='', verbose_name='SHA-256')
    size = models.PositiveIntegerField(default=0, verbose_name='Размер (байт)')
    received_at = models.DateTimeField(auto_now_add=True, verbose_name='Получена')
    email = models.ForeignKey(
        'Emails.Email', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='doc_revisions',
        verbose_name='Письмо',
    )
    attachment = models.ForeignKey(
        'Emails.Attachment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='doc_revisions',
        verbose_name='Вложение',
    )
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='manual', verbose_name='Источник')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='received', verbose_name='Статус')
    storage_path = models.CharField(max_length=500, blank=True, default='', verbose_name='Путь выдачи (сеть)')
    archive_path = models.CharField(max_length=500, blank=True, default='', verbose_name='Путь в архиве')
    submitted_folder = models.CharField(max_length=300, blank=True, default='', verbose_name='Папка Подано')
    task = models.ForeignKey(
        'ProjectTDL.TaskNode', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='doc_revisions',
        verbose_name='Задача',
    )
    accdb_task_code = models.CharField(
        max_length=20, blank=True, default='',
        verbose_name='Код задачи accdb',
        help_text='[02 Задачи].Код задачи до маппинга на TaskNode (DOC-5)',
    )

    def __str__(self):
        return f'{self.entry.code} rev{self.rev_no} [{self.get_status_display()}]'

    class Meta:
        verbose_name = 'Ревизия документации'
        verbose_name_plural = 'Ревизии документации'
        ordering = ['entry__code', 'rev_no']
        constraints = [
            # SQLite: NULL-записи не конфликтуют — интейки до register безопасны
            models.UniqueConstraint(fields=['entry', 'rev_no'], name='docregistry_rev_unique'),
        ]


class DocCheck(models.Model):
    """Результат валидации ревизии — шаг 2 (DesignBase, канон §2/§7)."""

    VERDICT_CHOICES = [('PASS', 'Годно'), ('FAIL', 'Замечания')]

    revision = models.OneToOneField(
        DocRevision, on_delete=models.CASCADE,
        related_name='validation', verbose_name='Ревизия',
    )
    verdict = models.CharField(max_length=4, choices=VERDICT_CHOICES, verbose_name='Вердикт')
    diff_json = models.JSONField(default=dict, blank=True, verbose_name='Что изменилось', help_text='листы/штампы/размеры из revision_diff')
    checks_json = models.JSONField(default=dict, blank=True, verbose_name='Проверки П1–П4')
    questions_md = models.TextField(blank=True, default='', verbose_name='Вопросы подрядчику')
    checked_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Проверил',
    )
    checked_at = models.DateTimeField(auto_now=True, verbose_name='Проверено')

    def __str__(self):
        return f'Проверка {self.revision} → {self.verdict}'

    class Meta:
        verbose_name = 'Проверка ревизии'
        verbose_name_plural = 'Проверки ревизий'


class DocRemark(models.Model):
    """Замечание + лист согласования — шаг 4а (канон §2)."""

    revision = models.ForeignKey(
        DocRevision, on_delete=models.CASCADE,
        related_name='remarks', verbose_name='Ревизия',
    )
    text = models.TextField(verbose_name='Текст замечания')
    sheet_pdf = models.FileField(
        upload_to='DocRegistry/remarks/%Y/%m/', null=True, blank=True,
        verbose_name='Лист согласования (PDF)',
    )
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='Отправлено')
    reply_at = models.DateTimeField(null=True, blank=True, verbose_name='Ответ получен')
    reply_file = models.FileField(
        upload_to='DocRegistry/remarks/%Y/%m/', null=True, blank=True,
        verbose_name='Ответ подрядчика',
    )

    def __str__(self):
        return f'Замечание к {self.revision}'

    class Meta:
        verbose_name = 'Замечание'
        verbose_name_plural = 'Замечания'
        ordering = ['-id']


class DocIssue(models.Model):
    """Выдача в производство работ — шаги 4б–5 (канон §2)."""

    entry = models.ForeignKey(
        DocRegisterEntry, on_delete=models.CASCADE,
        related_name='issues', verbose_name='Запись реестра',
    )
    waybill_no = models.CharField(max_length=50, verbose_name='№ накладной')
    waybill_date = models.DateField(null=True, blank=True, verbose_name='Дата накладной')
    waybill_pdf = models.FileField(
        upload_to='DocRegistry/issues/%Y/%m/', null=True, blank=True,
        verbose_name='Накладная (PDF)',
    )
    network_path = models.CharField(max_length=500, blank=True, default='', verbose_name='Папка выдачи (сеть)')
    archived_old_rev = models.BooleanField(default=False, verbose_name='Старая ревизия убрана в архив')
    issued_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Выдал',
    )
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name='Выдано')

    def __str__(self):
        return f'Выдача {self.entry.code} по накладной №{self.waybill_no}'

    class Meta:
        verbose_name = 'Выдача в ПР'
        verbose_name_plural = 'Выдачи в ПР'
        ordering = ['-issued_at']


class DocChangeLog(models.Model):
    """Журнал изменений реестра — история (аналог ContractChangeLog, канон §3)."""

    SOURCE_CHOICES = [
        ('manual', 'Руками'),
        ('api', 'API агента'),
        ('import', 'Импорт accdb'),
    ]

    entry = models.ForeignKey(
        DocRegisterEntry, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='changelog',
        verbose_name='Запись реестра',
    )
    revision = models.ForeignKey(
        DocRevision, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='changelog',
        verbose_name='Ревизия',
    )
    field = models.CharField(max_length=100, verbose_name='Поле')
    old_value = models.TextField(blank=True, default='', verbose_name='Было')
    new_value = models.TextField(blank=True, default='', verbose_name='Стало')
    changed_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Кто',
    )
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name='Когда')
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='manual', verbose_name='Источник')

    def __str__(self):
        return f'{self.entry or self.revision}: {self.field}'

    class Meta:
        verbose_name = 'Запись журнала РД'
        verbose_name_plural = 'Журнал изменений РД'
        ordering = ['-changed_at']
