"""Модели реестра РД: один объект — одна таблица.

Принцип: абстрактный базовый класс описывает структуру один раз,
конкретные таблицы М1/К1 наследуют его — данные объектов физически
не смешиваются (отдельные таблицы doc_m1_*, doc_k1_*).

Общее для всего приложения:
DocProject (шапка согласования) + справочники StaticData (типы зданий,
разделы почты) и собственные DocSection/DocDeveloper/DocSigner реестра.

Своё у каждого объекта (пары таблиц М1/К1): здания (номера свои),
записи реестра, ревизии, проверки, замечания, выдачи, журнал.
"""
from __future__ import annotations

from django.db import models
from django.http import Http404
from django.utils import timezone
from django.utils.deconstruct import deconstructible
from django.utils.functional import cached_property

#: Коды объектов-реестров. Новый объект = +7 классов ниже + строка в REGISTRIES.
PROJECT_CODES = ('M1', 'K1')


@deconstructible
class RegistryUploadTo:
    """Путь загрузки файла в папку своего объекта: DocRegistry/<M1|K1>/<subdir>/ГГГГ/ММ/.

    PROJECT_CODE берётся с конкретной таблицы (M1*/K1*), поэтому новые файлы
    объектов изначально лежат раздельно. Существующие пути в БД не трогаем.
    """

    def __init__(self, subdir):
        self.subdir = subdir

    def __call__(self, instance, filename):
        ts = timezone.now()
        return f'DocRegistry/{instance.PROJECT_CODE}/{self.subdir}/{ts:%Y/%m}/{filename}'


class DocProject(models.Model):
    """Проект: шапка листа согласования (заказчик/объект/проектировщик).

    М1 — Волоколамск (детальные данные), К1 — Калуга. Несколько проектов
    в одном листе — таблицей (см. approval_sheet_multi)."""

    code = models.CharField(max_length=10, primary_key=True, verbose_name='Код проекта')
    name = models.CharField(max_length=200, blank=True, default='', verbose_name='Название')
    customer = models.CharField(max_length=300, blank=True, default='', verbose_name='Заказчик')
    object_name = models.CharField(max_length=500, blank=True, default='', verbose_name='Объект')
    object_address = models.CharField(max_length=500, blank=True, default='', verbose_name='Адрес объекта')
    designer = models.CharField(max_length=200, blank=True, default='', verbose_name='Проектировщик')

    def __str__(self):
        return f'{self.code} — {self.name}' if self.name else self.code

    @property
    def object_full(self):
        addr = f', {self.object_address}' if self.object_address else ''
        return f'{self.object_name}{addr}'

    class Meta:
        verbose_name = 'Проект (шапка согласования)'
        verbose_name_plural = 'Проекты (шапка согласования)'
        ordering = ['code']


class BaseRegistryBuilding(models.Model):
    """Здание реестра объекта — зеркало [Здания] accdb (абстрактно).

    Конкретная таблица принадлежит одному объекту (M1Building/K1Building),
    поэтому поля project нет: смешивание невозможно конструктивно.
    Тип здания — общий справочник StaticData (один на всё приложение).
    """

    code = models.IntegerField(unique=True, db_index=True, verbose_name='Код здания')
    building_type = models.ForeignKey(
        'StaticData.BuildingType', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name='Тип здания',
        help_text='Общий справочник (Справочники → Здания Тип); номер — свой у объекта',
    )
    number = models.CharField(max_length=20, blank=True, default='', verbose_name='№ здания')
    name = models.CharField(max_length=200, blank=True, default='', verbose_name='Наименование здания')

    #: Код объекта конкретной таблицы ('M1'/'K1') — задаётся в наследнике.
    PROJECT_CODE = ''

    def __str__(self):
        return self.name or f'Здание {self.code}'

    class Meta:
        abstract = True
        ordering = ['code']


class DocSection(models.Model):
    """Раздел — зеркало [Разделы] accdb. Код = первичный ключ."""

    code = models.IntegerField(primary_key=True, verbose_name='Код раздела')
    short = models.CharField(max_length=20, blank=True, default='', verbose_name='Раздел (шифр)')
    name = models.CharField(max_length=200, blank=True, default='', verbose_name='Наименование раздела')

    def __str__(self):
        return self.short or f'Раздел {self.code}'

    class Meta:
        verbose_name = 'Раздел (справочник РД)'
        verbose_name_plural = 'Разделы (справочник РД)'
        ordering = ['code']


class DocDeveloper(models.Model):
    """Разработчик — зеркало [Разработчик] accdb. Код = первичный ключ."""

    code = models.IntegerField(primary_key=True, verbose_name='Код')
    name = models.CharField(max_length=200, blank=True, default='', verbose_name='Разработчик')

    def __str__(self):
        return self.name or f'Разработчик {self.code}'

    class Meta:
        verbose_name = 'Разработчик (справочник РД)'
        verbose_name_plural = 'Разработчики (справочник РД)'
        ordering = ['code']


class DocSigner(models.Model):
    """Подписант листа согласования — единый общий список."""

    position = models.CharField(max_length=200, blank=True, default='', verbose_name='Должность')
    company = models.CharField(max_length=200, blank=True, default='', verbose_name='Компания')
    person = models.CharField(max_length=200, blank=True, default='', verbose_name='ФИО')
    mark = models.CharField(max_length=100, blank=True, default='', verbose_name='Отметка')
    stamp = models.BooleanField(
        default=False, verbose_name='Штамп «Согласовано»',
        help_text='В ячейке подписи — штамп СОГЛАСОВАНО + ФИО + дата/время (как э-подпись)',
    )
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    def __str__(self):
        return f'{self.position.strip()} — {self.person}'

    class Meta:
        verbose_name = 'Подписант'
        verbose_name_plural = 'Подписанты'
        ordering = ['order']


class BaseRegistryEntry(models.Model):
    """Строка реестра РД — зеркало [01 Реестр] accdb объекта (канон §3, абстрактно).

    Маппинг колонок accdb 1:1 (исходные имена — в help_text).
    История — цепочкой ревизий, старые строки не правятся.
    FK на здания задаются в наследниках (таблица здания — своя у объекта).
    """

    code = models.PositiveIntegerField(unique=True, verbose_name='Код', help_text='accdb: код')
    # В accdb раздел/разработчик — КОДЫ справочников, не текст:
    # раздел → [Разделы].код раздела, разраб_нов → [Разработчик].Код.
    section = models.ForeignKey(
        DocSection, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name='Раздел', help_text='accdb: раздел (код)',
    )
    cipher = models.CharField(max_length=200, blank=True, default='', db_index=True, verbose_name='Шифр', help_text='accdb: шифр')
    file_name = models.CharField(max_length=1000, blank=True, default='', verbose_name='Имя эл. файла', help_text='accdb: Назв Эл файла (max 771 в live)')
    approval_status = models.CharField(max_length=50, blank=True, default='', verbose_name='Согласование', help_text='accdb: согласование')
    approval_date = models.DateField(null=True, blank=True, verbose_name='Дата согласования', help_text='accdb: дата согласования')
    submitted_flag = models.CharField(max_length=10, blank=True, default='', verbose_name='Подано', help_text='accdb: подано на согласование')
    change_descr = models.TextField(blank=True, default='', verbose_name='Описание изменений', help_text='accdb: Описание изм')
    submit_date = models.DateField(null=True, blank=True, verbose_name='Дата подачи', help_text='accdb: Дата подачи на согласование')
    acts = models.CharField(max_length=500, blank=True, default='', verbose_name='Акты', help_text='accdb: Акты (max 289 в live)')
    developer = models.ForeignKey(
        DocDeveloper, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name='Разраб.', help_text='accdb: разраб_нов (код)',
    )
    contract = models.ForeignKey(
        'ProjectContract.Contract', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name='Договор',
    )
    accdb_row_hash = models.CharField(
        max_length=64, blank=True, default='',
        verbose_name='Хеш строки accdb',
        help_text='sha1 конкатенации полей — для ночного check_accdb_drift (DOC-5)',
    )

    #: Код объекта конкретной таблицы ('M1'/'K1') — задаётся в наследнике.
    PROJECT_CODE = ''

    def __str__(self):
        return f'{self.code}: {self.cipher or self.file_name}'[:120]

    @cached_property
    def project(self):
        """Шапка согласования своего объекта (для печатных форм)."""
        return DocProject.objects.get(pk=self.PROJECT_CODE)

    @property
    def project_id(self):
        return self.PROJECT_CODE

    class Meta:
        abstract = True
        ordering = ['code']


class BaseRegistryRevision(models.Model):
    """Файл ревизии документации — шаг 1–2 конвейера (канон §2, абстрактно).

    FK на запись реестра — в наследниках (таблица записи — своя у объекта).
    """

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

    rev_no = models.PositiveIntegerField(default=1, verbose_name='№ ревизии')
    file = models.FileField(
        upload_to=RegistryUploadTo('incoming'), null=True, blank=True,
        verbose_name='Файл ревизии',
    )
    sha256 = models.CharField(max_length=64, blank=True, default='', verbose_name='SHA-256')
    size = models.PositiveIntegerField(default=0, verbose_name='Размер (байт)')
    received_at = models.DateTimeField(auto_now_add=True, verbose_name='Получена')
    email = models.ForeignKey(
        'Emails.Email', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name='Письмо',
    )
    attachment = models.ForeignKey(
        'Emails.Attachment', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name='Вложение',
    )
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='manual', verbose_name='Источник')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='received', verbose_name='Статус')
    storage_path = models.CharField(max_length=500, blank=True, default='', verbose_name='Путь выдачи (сеть)')
    archive_path = models.CharField(max_length=500, blank=True, default='', verbose_name='Путь в архиве')
    submitted_folder = models.CharField(max_length=300, blank=True, default='', verbose_name='Папка Подано')
    task = models.ForeignKey(
        'ProjectTDL.TaskNode', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        verbose_name='Задача',
    )
    accdb_task_code = models.CharField(
        max_length=20, blank=True, default='',
        verbose_name='Код задачи accdb',
        help_text='[02 Задачи].Код задачи до маппинга на TaskNode (DOC-5)',
    )

    PROJECT_CODE = ''

    def __str__(self):
        return f'{self.entry.code} rev{self.rev_no} [{self.get_status_display()}]'

    class Meta:
        abstract = True
        ordering = ['entry__code', 'rev_no']


class BaseRegistryCheck(models.Model):
    """Результат валидации ревизии — шаг 2 (DesignBase, канон §2/§7, абстрактно)."""

    VERDICT_CHOICES = [('PASS', 'Годно'), ('FAIL', 'Замечания')]

    verdict = models.CharField(max_length=4, choices=VERDICT_CHOICES, verbose_name='Вердикт')
    diff_json = models.JSONField(default=dict, blank=True, verbose_name='Что изменилось', help_text='листы/штампы/размеры из revision_diff')
    checks_json = models.JSONField(default=dict, blank=True, verbose_name='Проверки П1–П4')
    questions_md = models.TextField(blank=True, default='', verbose_name='Вопросы подрядчику')
    checked_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Проверил',
    )
    checked_at = models.DateTimeField(auto_now=True, verbose_name='Проверено')

    PROJECT_CODE = ''

    def __str__(self):
        return f'Проверка {self.revision} → {self.verdict}'

    class Meta:
        abstract = True


class BaseRegistryRemark(models.Model):
    """Замечание + лист согласования — шаг 4а (канон §2, абстрактно).

    Новые замечания привязаны к revision; исторические из accdb
    ([Замечания к чертежам] по Код реестра) — к entry напрямую.
    """

    text = models.TextField(verbose_name='Текст замечания')
    author = models.CharField(max_length=200, blank=True, default='', verbose_name='Автор')
    remark_date = models.DateField(null=True, blank=True, verbose_name='Дата замечания')
    sheet_pdf = models.FileField(
        upload_to=RegistryUploadTo('remarks'), null=True, blank=True,
        verbose_name='Лист согласования (PDF)',
    )
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='Отправлено')
    reply_at = models.DateTimeField(null=True, blank=True, verbose_name='Ответ получен')
    reply_file = models.FileField(
        upload_to=RegistryUploadTo('remarks'), null=True, blank=True,
        verbose_name='Ответ подрядчика',
    )

    PROJECT_CODE = ''

    def __str__(self):
        return f'Замечание к {self.revision}'

    class Meta:
        abstract = True
        ordering = ['-id']


class BaseRegistryIssue(models.Model):
    """Выдача в производство работ — шаги 4б–5 (канон §2, абстрактно)."""

    waybill_no = models.CharField(max_length=50, verbose_name='№ накладной')
    waybill_date = models.DateField(null=True, blank=True, verbose_name='Дата накладной')
    waybill_pdf = models.FileField(
        upload_to=RegistryUploadTo('issues'), null=True, blank=True,
        verbose_name='Накладная (PDF)',
    )
    network_path = models.CharField(max_length=500, blank=True, default='', verbose_name='Папка выдачи (сеть)')
    approval_pdf = models.FileField(
        upload_to=RegistryUploadTo('issues'), null=True, blank=True,
        verbose_name='Лист согласования (PDF)',
    )
    archived_old_rev = models.BooleanField(default=False, verbose_name='Старая ревизия убрана в архив')
    issued_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Выдал',
    )
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name='Выдано')

    PROJECT_CODE = ''

    def __str__(self):
        return f'Выдача {self.entry.code} по накладной №{self.waybill_no}'

    class Meta:
        abstract = True
        ordering = ['-issued_at']


class BaseRegistryChangeLog(models.Model):
    """Журнал изменений реестра — история (аналог ContractChangeLog, канон §3, абстрактно)."""

    SOURCE_CHOICES = [
        ('manual', 'Руками'),
        ('api', 'API агента'),
        ('import', 'Импорт accdb'),
    ]

    field = models.CharField(max_length=100, verbose_name='Поле')
    old_value = models.TextField(blank=True, default='', verbose_name='Было')
    new_value = models.TextField(blank=True, default='', verbose_name='Стало')
    changed_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Кто',
    )
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name='Когда')
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='manual', verbose_name='Источник')

    PROJECT_CODE = ''

    def __str__(self):
        return f'{self.entry or self.revision}: {self.field}'

    class Meta:
        abstract = True
        ordering = ['-changed_at']


# ----------------------------------------------------------------------------
# Конкретные реестры объектов: М1 и К1. Таблицы doc_m1_*, doc_k1_*.
# ----------------------------------------------------------------------------

class M1Building(BaseRegistryBuilding):
    PROJECT_CODE = 'M1'

    class Meta:
        db_table = 'doc_m1_building'
        verbose_name = 'Здание М1'
        verbose_name_plural = 'Здания М1'
        ordering = ['code']


class K1Building(BaseRegistryBuilding):
    PROJECT_CODE = 'K1'

    class Meta:
        db_table = 'doc_k1_building'
        verbose_name = 'Здание К1'
        verbose_name_plural = 'Здания К1'
        ordering = ['code']


class M1Entry(BaseRegistryEntry):
    """Строка реестра М1 — зеркало [01 Реестр] М1.accdb."""

    building_no = models.ForeignKey(
        M1Building, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='entries_by_number',
        verbose_name='Номер здания', help_text='accdb: Номер здания (код)',
    )
    building = models.ForeignKey(
        M1Building, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='entries',
        verbose_name='Наименование здания', help_text='accdb: Наименование здания (код)',
    )

    PROJECT_CODE = 'M1'

    class Meta:
        db_table = 'doc_m1_entry'
        verbose_name = 'Запись реестра М1'
        verbose_name_plural = 'Реестр М1'
        ordering = ['code']


class K1Entry(BaseRegistryEntry):
    """Строка реестра К1 — зеркало [01 Реестр] К1.accdb."""

    building_no = models.ForeignKey(
        K1Building, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='entries_by_number',
        verbose_name='Номер здания', help_text='accdb: Номер здания (код)',
    )
    building = models.ForeignKey(
        K1Building, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='entries',
        verbose_name='Наименование здания', help_text='accdb: Наименование здания (код)',
    )

    PROJECT_CODE = 'K1'

    class Meta:
        db_table = 'doc_k1_entry'
        verbose_name = 'Запись реестра К1'
        verbose_name_plural = 'Реестр К1'
        ordering = ['code']


class M1Revision(BaseRegistryRevision):
    entry = models.ForeignKey(
        M1Entry, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='revisions', verbose_name='Запись реестра',
        help_text='Пусто до шага 3 (register) — приём идёт раньше привязки к реестру',
    )

    PROJECT_CODE = 'M1'

    class Meta:
        db_table = 'doc_m1_revision'
        verbose_name = 'Ревизия М1'
        verbose_name_plural = 'Ревизии М1'
        ordering = ['entry__code', 'rev_no']
        constraints = [
            # SQLite: NULL-записи не конфликтуют — интейки до register безопасны
            models.UniqueConstraint(fields=['entry', 'rev_no'], name='doc_m1_rev_unique'),
        ]


class K1Revision(BaseRegistryRevision):
    entry = models.ForeignKey(
        K1Entry, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='revisions', verbose_name='Запись реестра',
        help_text='Пусто до шага 3 (register) — приём идёт раньше привязки к реестру',
    )

    PROJECT_CODE = 'K1'

    class Meta:
        db_table = 'doc_k1_revision'
        verbose_name = 'Ревизия К1'
        verbose_name_plural = 'Ревизии К1'
        ordering = ['entry__code', 'rev_no']
        constraints = [
            models.UniqueConstraint(fields=['entry', 'rev_no'], name='doc_k1_rev_unique'),
        ]


class M1Check(BaseRegistryCheck):
    revision = models.OneToOneField(
        M1Revision, on_delete=models.CASCADE,
        related_name='validation', verbose_name='Ревизия',
    )

    PROJECT_CODE = 'M1'

    class Meta:
        db_table = 'doc_m1_check'
        verbose_name = 'Проверка М1'
        verbose_name_plural = 'Проверки М1'


class K1Check(BaseRegistryCheck):
    revision = models.OneToOneField(
        K1Revision, on_delete=models.CASCADE,
        related_name='validation', verbose_name='Ревизия',
    )

    PROJECT_CODE = 'K1'

    class Meta:
        db_table = 'doc_k1_check'
        verbose_name = 'Проверка К1'
        verbose_name_plural = 'Проверки К1'


class M1Remark(BaseRegistryRemark):
    revision = models.ForeignKey(
        M1Revision, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='remarks', verbose_name='Ревизия',
    )
    entry = models.ForeignKey(
        M1Entry, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='history_remarks', verbose_name='Запись реестра (история)',
    )

    PROJECT_CODE = 'M1'

    class Meta:
        db_table = 'doc_m1_remark'
        verbose_name = 'Замечание М1'
        verbose_name_plural = 'Замечания М1'
        ordering = ['-id']


class K1Remark(BaseRegistryRemark):
    revision = models.ForeignKey(
        K1Revision, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='remarks', verbose_name='Ревизия',
    )
    entry = models.ForeignKey(
        K1Entry, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='history_remarks', verbose_name='Запись реестра (история)',
    )

    PROJECT_CODE = 'K1'

    class Meta:
        db_table = 'doc_k1_remark'
        verbose_name = 'Замечание К1'
        verbose_name_plural = 'Замечания К1'
        ordering = ['-id']


class M1Issue(BaseRegistryIssue):
    entry = models.ForeignKey(
        M1Entry, on_delete=models.CASCADE,
        related_name='issues', verbose_name='Запись реестра',
    )

    PROJECT_CODE = 'M1'

    class Meta:
        db_table = 'doc_m1_issue'
        verbose_name = 'Выдача М1'
        verbose_name_plural = 'Выдачи М1'
        ordering = ['-issued_at']


class K1Issue(BaseRegistryIssue):
    entry = models.ForeignKey(
        K1Entry, on_delete=models.CASCADE,
        related_name='issues', verbose_name='Запись реестра',
    )

    PROJECT_CODE = 'K1'

    class Meta:
        db_table = 'doc_k1_issue'
        verbose_name = 'Выдача К1'
        verbose_name_plural = 'Выдачи К1'
        ordering = ['-issued_at']


class M1ChangeLog(BaseRegistryChangeLog):
    entry = models.ForeignKey(
        M1Entry, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='changelog',
        verbose_name='Запись реестра',
    )
    revision = models.ForeignKey(
        M1Revision, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='changelog',
        verbose_name='Ревизия',
    )

    PROJECT_CODE = 'M1'

    class Meta:
        db_table = 'doc_m1_changelog'
        verbose_name = 'Запись журнала М1'
        verbose_name_plural = 'Журнал М1'
        ordering = ['-changed_at']


class K1ChangeLog(BaseRegistryChangeLog):
    entry = models.ForeignKey(
        K1Entry, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='changelog',
        verbose_name='Запись реестра',
    )
    revision = models.ForeignKey(
        K1Revision, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='changelog',
        verbose_name='Ревизия',
    )

    PROJECT_CODE = 'K1'

    class Meta:
        db_table = 'doc_k1_changelog'
        verbose_name = 'Запись журнала К1'
        verbose_name_plural = 'Журнал К1'
        ordering = ['-changed_at']


#: Карта реестров: код объекта → модели его таблиц. Единая точка выбора.
REGISTRIES = {
    'M1': {
        'building': M1Building, 'entry': M1Entry, 'revision': M1Revision,
        'check': M1Check, 'remark': M1Remark, 'issue': M1Issue,
        'changelog': M1ChangeLog,
    },
    'K1': {
        'building': K1Building, 'entry': K1Entry, 'revision': K1Revision,
        'check': K1Check, 'remark': K1Remark, 'issue': K1Issue,
        'changelog': K1ChangeLog,
    },
}


def get_registry_or_404(project_code):
    """Модели таблиц объекта; неизвестный код — 404."""
    try:
        return REGISTRIES[project_code]
    except KeyError:
        raise Http404(f'Нет реестра объекта {project_code!r}')
