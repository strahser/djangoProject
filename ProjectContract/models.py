import datetime
from decimal import Decimal

import pandas as pd
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.db.models import F, Sum, Max, Min, DateField
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib import admin

class BaseModel(models.Model):
	creation_stamp = models.DateTimeField(auto_now_add=True, null=True, verbose_name="дата создания")
	update_stamp = models.DateTimeField(auto_now=True, null=True, verbose_name="дата изменения")

	class Meta:
		abstract = True

class DataSceldualModels(models.Model):
	creation_stamp = models.DateTimeField(auto_now_add=True, null=True, verbose_name="дата создания")
	update_stamp = models.DateTimeField(auto_now=True, null=True, verbose_name="дата изменения")


	class Meta:
		abstract = True

class Contractor(BaseModel):
	name = models.CharField(max_length=200, null=True, verbose_name='Подрядчик')

	class Meta:
		verbose_name = 'Подрядчик'
		verbose_name_plural = 'Подрядчики'

	def __str__(self):
		return self.name


CONTRACT_STAGES = (
	('negotiation', 'Переговоры'),
	('signing', 'Подписание'),
	('advance', 'Аванс'),
	('execution', 'Выполнение работ'),
	('acceptance', 'Приёмка'),
	('final_payment', 'Окончательный расчёт'),
	('warranty', 'Гарантия'),
	('closed', 'Закрыт'),
)


class Contract(BaseModel):
	CONTRACT_STATUS = (
		('draft', 'Черновик'),
		('active', 'Действующий'),
		('suspended', 'Приостановлен'),
		('closed', 'Завершён'),
		('canceled', 'Расторгнут'),
	)
	project_site = models.ForeignKey('StaticData.ProjectSite', verbose_name='Проект',
	                                 null=False,
	                                 on_delete=models.CASCADE
	                                 )
	contractor = models.ForeignKey('ProjectContract.Contractor', on_delete=models.CASCADE, verbose_name='Подрядчик')
	client = models.ForeignKey('ProjectContract.Contractor', null=True, blank=True,
	                           on_delete=models.SET_NULL, related_name='client_contracts',
	                           verbose_name='Заказчик')
	name = models.CharField(max_length=200, null=True, verbose_name='Описание')
	number = models.CharField(max_length=100, null=True, blank=True, verbose_name='Номер договора')
	sign_date = models.DateField(null=True, blank=True, verbose_name='Дата подписания')
	status = models.CharField(max_length=20, choices=CONTRACT_STATUS, default='active',
	                          verbose_name='Статус')
	stage = models.CharField(max_length=20, choices=CONTRACT_STAGES, default='negotiation',
	                         verbose_name='Этап')
	next_step = models.CharField(max_length=200, null=True, blank=True,
	                             verbose_name='Следующий шаг')
	next_step_date = models.DateField(null=True, blank=True,
	                                  verbose_name='Дата следующего шага')
	parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL,
	                           related_name='children', verbose_name='Головной договор (субподряд)')
	price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="цена договора", default=0)
	estimate = models.ForeignKey('ProjectContract.ContractEstimate', null=True, blank=True,
	                             on_delete=models.SET_NULL, related_name='contracts_main',
	                             verbose_name='Основная смета')
	proposal_number = models.CharField(max_length=200, null=True, blank=True, verbose_name='Proposal')
	proposal_link = models.TextField(max_length=300, null=True, blank=True, verbose_name='Proposal link')
	start_date = models.DateField(verbose_name="план.начало", null=True, blank=True,default=datetime.date.today )
	duration = models.FloatField(verbose_name="длительность", null=True, blank=True, default=1)
	due_date = models.DateField(verbose_name="план.завершение", null=True, blank=True,default=datetime.date.today)
	tags = models.ManyToManyField('Tag', blank=True, related_name='contracts',
	                              verbose_name='Теги')

	class Meta:
		verbose_name = 'Договор'
		verbose_name_plural = 'Договоры'

	def __str__(self):
		return self.name



class ContractPayments(BaseModel):
	PAYMENT_TYPES = (
		('advance', 'Аванс'),
		('intermediate', 'промежуточный '),
		('final', 'финальный'),
	)
	CALC_TYPES = (
		('manual', 'Вручную (фиксированная цена)'),
		('percent_of_contract', 'Доля от цены договора'),
		('percent_of_base', 'Доля от фиксированной суммы'),
		('percent_of_parent', 'Доля от родительского платежа'),
	)
	PAYMENT_STATUS = (
		('planned', 'Запланирован'),
		('guaranteed', 'Гарантирован'),
		('high_prob', 'Высокая вероятность'),
		('low_prob', 'Низкая вероятность'),
		('approved', 'Согласован'),
		('invoiced', 'Выставлен счёт'),
		('partially_paid', 'Частично оплачен'),
		('paid', 'Оплачен'),
	)
	name = models.CharField(max_length=200,null=True, verbose_name='Наименование платежа')
	payment_type = models.CharField(max_length=200, choices=PAYMENT_TYPES, default='advance',
	                                verbose_name='Тип платежа', null=True, blank=True)
	payment_description = models.TextField(verbose_name="Описание платежа", null=True, blank=True, )
	price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="цена", default=0)
	contract = models.ForeignKey('ProjectContract.Contract', on_delete=models.CASCADE, verbose_name='Договор')
	percent = models.FloatField(verbose_name="доля (0..1)", null=True, blank=True, )
	calc_type = models.CharField(max_length=30, choices=CALC_TYPES, default='manual',
	                             verbose_name='Тип расчёта цены')
	base_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
	                                  verbose_name="Сумма-база для доли")
	parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children',
	                           verbose_name="Зависимость")
	made_payment = models.BooleanField(verbose_name='Оплачено?', default=False)
	status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='planned',
	                          verbose_name='Статус')
	paid_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
	                                  verbose_name="Оплачено (факт)")
	paid_date = models.DateField(null=True, blank=True, verbose_name="Дата оплаты (факт)")
	invoice_number = models.CharField(max_length=100, null=True, blank=True,
	                                  verbose_name='Номер счёта')
	start_date = models.DateField(verbose_name="план.начало", null=True, blank=True, default=None)
	duration = models.FloatField(verbose_name="длительность", null=True, blank=True, default=None)
	due_date = models.DateField(verbose_name="план.завершение", null=True, blank=True, default=None)
	class Meta:
		verbose_name = 'договор Оплата'
		verbose_name_plural = 'договоры Оплаты'
		ordering = ["id"]

	def __str__(self):
		return str(self.id)

	@admin.display(description="Подрядчик", ordering="contract__contractor__name")
	def contractor_name(self):
		return self.contract.contractor

	@admin.display(description="Проект", ordering="contract__project_site")
	def project_site(self):
		return self.contract.project_site

	def save(self, *args, **kwargs):
		# Вся бизнес-логика — в ProjectContract.services (чистые функции):
		# цена по типу расчёта, собственные даты, затем один bulk-пересчёт
		# цепочки потомков (без рекурсивных save).
		# Статус — источник истины для флага made_payment (прокси для фильтров).
		from .services import compute_price, compute_own_dates, propagate_dates
		new_price = compute_price(self)
		if new_price is not None:
			self.price = new_price
		self.made_payment = (self.status == 'paid')
		if self.status == 'paid' and self.paid_amount is None:
			self.paid_amount = self.price
		compute_own_dates(self)
		super().save(*args, **kwargs)
		propagate_dates(self)

	def update_due_date(self):
		"""
        Обновляет дату окончания платежа, если изменились дата начала или длительность.
        """
		if self.start_date and self.duration:
			self.due_date = self.start_date + timezone.timedelta(days = self.duration)
			self.save()

	def update_start_date(self):
		"""
        Обновляет дату начала платежа, если изменился предшественник.
        """
		if self.parent:
			self.start_date = self.parent.due_date
			self.save()

	def update_children(self):
		"""
        Пересчитывает даты всех дочерних платежей (один bulk_update, без рекурсии).
        """
		from .services import propagate_dates
		return propagate_dates(self)


class PaymentCalendar(models.Model):
	contract = models.ForeignKey('Contract', on_delete=models.CASCADE, verbose_name='Договор')
	date = models.DateField(verbose_name='Дата')
	contract_payment = models.ForeignKey(ContractPayments, null=True, blank=True, on_delete=models.CASCADE)
	payment_value = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Сумма платежа")

	class Meta:
		verbose_name = 'Календарь платежей'
		verbose_name_plural = 'Календари платежей'
		ordering = ["date"]
		abstract = True

	def __str__(self):
		return f"Календарь платежей для договора {self.contract.name} - {self.date}"

	@staticmethod
	def make_link(name: str, pk: int):
		"""

        :param name: навзвание гиперссылки
        :param pk: pk модели
        :return: навзвание гиперссылки без гиперссылки
        """
		try:
			_reverse = reverse('admin:ProjectContract_contractpayments_change',
			                   args=[pk])
			return format_html(f'<a href="{_reverse}">{name}</a>')
		except ContractPayments.DoesNotExist:
			return name

	@staticmethod
	def populate_scale(scale: str, schedule_data: pd.DataFrame) -> pd.DataFrame:
		scale_periods = {
			'week': 'W',
			'month': 'M',
			'quarter': 'Q',
			'day': 'D'
		}
		schedule_data['date'] = pd.to_datetime(schedule_data['date']).dt.date  # Convert dates to date objects

		if scale in scale_periods:
			schedule_data['date'] = pd.to_datetime(schedule_data['date']) \
				.dt.to_period(scale_periods[scale])
		return schedule_data

	@staticmethod
	def generate_calendar(contract: Contract, scale: str = "week",
	                      contract_payment_filter: ContractPayments = None) -> pd.DataFrame:
		"""
        Генерирует календарь платежей для договора.
        """
		# Получаем платежи для договора
		if contract_payment_filter:
			payments = contract_payment_filter.filter(contract=contract).all()
		else:
			payments = ContractPayments.objects.filter(contract=contract).all()
		payments = [p for p in payments if p.due_date and p.price]
		# Создаем DataFrame с информацией о платежах
		df = pd.DataFrame({
			'date': [payment.due_date for payment in payments],
			'payment_value': [payment.price for payment in payments],
			'contract__name': [contract.name for payment in payments],
			'contract__contractpayments__name': [PaymentCalendar.make_link(payment.name, payment.id) for payment in
			                                     payments]
		})
		# Преобразуем даты в нужный масштаб
		df = PaymentCalendar.populate_scale(scale, df)
		return df

	@staticmethod
	def generate_payment_schedule(contract, scale="day"):
		"""
        Генерирует график платежей для договора.
        """
		payments = ContractPayments.objects.filter(contract=contract)\
			.exclude(start_date=None).exclude(due_date=None)
		df_columns_data = {
			'start_date': [payment.start_date for payment in payments],
			'due_date': [payment.due_date for payment in payments],
			'payment_value': [float(payment.price) / ((payment.duration or 0) if (payment.duration or 0) > 0 else 1) for payment in
			                  payments],  # Convert to float
			'contract__name': [contract.name for payment in payments],  # Add contract__name
			'contract__contractpayments__name': [PaymentCalendar.make_link(payment.name, payment.id)
			                                     for payment in payments],
			'duration': [payment.duration for payment in payments]
		}

		# Создаем DataFrame с информацией о платежах
		df = pd.DataFrame(df_columns_data)
		payment_dates = []
		payment_values = []
		contract_names = []  # Add a list to store contract names
		payment_names = []  # Add a list to store payment names

		for index, row in df.iterrows():
			# Generate dates with a frequency matching the duration
			dur = int(row['duration'] or 1)
			dates = pd.date_range(start=row['start_date'], end=row['due_date'], periods=dur)
			payment_dates.extend(dates.to_pydatetime())
			# Create a list of payment values for the duration (convert to int)
			payment_values.extend([float(row['payment_value'])] * dur)
			# Add contract name for each payment
			contract_names.extend([row['contract__name']] * dur)
			# Add payment name for each payment
			payment_names.extend([row['contract__contractpayments__name']] * dur)
		# Now both lists should have the same length
		schedule_data = pd.DataFrame({
			'date': payment_dates,
			'payment_value': payment_values,
			'contract__name': contract_names,  # Add contract__name to schedule_data
			'contract__contractpayments__name': payment_names  # Add contract__contractpayments__name to schedule_data
		})

		# Group by scale
		schedule_data = PaymentCalendar.populate_scale(scale, schedule_data)
		return schedule_data


class ConcretePaymentCalendar(PaymentCalendar):
	# This is the concrete model that will be registered with admin
	class Meta:
		verbose_name = "ДДС"
		verbose_name_plural = "ДДС"


class ContractChangeLog(BaseModel):
	"""Журнал изменений договоров, платежей и задач (C4/D6, DMX-1).

	Кто/что/когда: пользователь (None = система/агент), действие, подробности.
	Связи SET_NULL — записи переживают удаление договора/платежа/задачи.
	"""
	contract = models.ForeignKey('ProjectContract.Contract', null=True, blank=True,
	                             on_delete=models.SET_NULL, related_name='change_logs',
	                             verbose_name='Договор')
	payment = models.ForeignKey('ProjectContract.ContractPayments', null=True, blank=True,
	                            on_delete=models.SET_NULL, related_name='change_logs',
	                            verbose_name='Платёж')
	task = models.ForeignKey('ProjectTDL.TaskNode', null=True, blank=True,
	                         on_delete=models.SET_NULL, related_name='change_logs',
	                         verbose_name='Задача')
	action = models.CharField(max_length=50, verbose_name='Действие')
	details = models.TextField(blank=True, default='', verbose_name='Подробности')
	user = models.ForeignKey('auth.User', null=True, blank=True,
	                         on_delete=models.SET_NULL, verbose_name='Кто')

	class Meta:
		verbose_name = 'Изменение договора/платежа'
		verbose_name_plural = 'Журнал изменений'
		ordering = ['-creation_stamp', '-id']

	def __str__(self):
		target = self.payment or self.task or self.contract
		return f'{self.creation_stamp:%d.%m.%Y %H:%M} {self.action} {target}'


class ContractReminder(BaseModel):
	"""Ручное напоминание по договору/задаче/платежу (DMX-2, C9).

	Создаётся кнопкой «Напомнить» в карточках; команда check_reminders
	сообщает о наступивших (due_date <= сегодня, не отправлено, не закрыто).
	Связи SET_NULL — записи переживают удаление объектов.
	"""
	contract = models.ForeignKey('ProjectContract.Contract', null=True, blank=True,
	                             on_delete=models.SET_NULL, related_name='reminders',
	                             verbose_name='Договор')
	task = models.ForeignKey('ProjectTDL.TaskNode', null=True, blank=True,
	                         on_delete=models.SET_NULL, related_name='reminders',
	                         verbose_name='Задача')
	payment = models.ForeignKey('ProjectContract.ContractPayments', null=True, blank=True,
	                            on_delete=models.SET_NULL, related_name='reminders',
	                            verbose_name='Платёж')
	due_date = models.DateField(verbose_name='Напомнить не позже')
	message = models.CharField(max_length=255, blank=True, default='',
	                           verbose_name='Текст')
	recipient = models.ForeignKey('auth.User', null=True, blank=True,
	                              on_delete=models.SET_NULL, related_name='assigned_reminders',
	                              verbose_name='Кому')
	created_by = models.ForeignKey('auth.User', null=True, blank=True,
	                               on_delete=models.SET_NULL, related_name='created_reminders',
	                               verbose_name='Кто создал')
	is_sent = models.BooleanField(default=False, verbose_name='Уведомлено')
	sent_at = models.DateTimeField(null=True, blank=True, verbose_name='Когда уведомлено')
	is_done = models.BooleanField(default=False, verbose_name='Закрыто')

	class Meta:
		verbose_name = 'Напоминание'
		verbose_name_plural = 'Напоминания'
		ordering = ['due_date', '-id']

	def __str__(self):
		target = self.task or self.payment or self.contract
		return f'{self.due_date:%d.%m.%Y} {target}: {self.message or "напоминание"}'

	@property
	def is_due(self):
		"""Наступило и требует внимания (не отправлено, не закрыто)."""
		from datetime import date as _date
		return not self.is_sent and not self.is_done and self.due_date <= _date.today()


class ContractStageLog(BaseModel):
	"""Журнал этапов договора (DMC-5, C3/D2).

	Этап + дата + кто + заметки. Запись с is_next_step=True — запланированный
	шаг (напоминание); при переходе transition_contract_stage() плановые флаги
	договора сбрасываются, текущий этап пишется в Contract.stage.
	"""
	contract = models.ForeignKey('ProjectContract.Contract', on_delete=models.CASCADE,
	                             related_name='stage_logs', verbose_name='Договор')
	stage = models.CharField(max_length=20, choices=CONTRACT_STAGES, verbose_name='Этап')
	date = models.DateField(default=datetime.date.today, verbose_name='Дата')
	user = models.ForeignKey('auth.User', null=True, blank=True,
	                         on_delete=models.SET_NULL, verbose_name='Кто')
	notes = models.TextField(blank=True, default='', verbose_name='Заметки')
	is_next_step = models.BooleanField(default=False, verbose_name='Запланированный шаг')

	class Meta:
		verbose_name = 'Этап договора'
		verbose_name_plural = 'Этапы договоров (журнал)'
		ordering = ['-date', '-id']

	def __str__(self):
		return f'{self.contract} — {self.get_stage_display()} ({self.date:%d.%m.%Y})'


class CashflowEntry(BaseModel):
	"""Материализованная строка ДДС (Ф2).

	Один платёж → 1–2 строки (частичная оплата: факт + остаток-прогноз).
	Пересчёт — rebuild_cashflow() по сигналу save/delete платежа.
	Агрегация по day/week/month/quarter — в запросе (Trunc*), хранения
	по масштабам не требуется.
	"""
	BUCKETS = (
		('fact', 'Факт'),
		('guaranteed', 'Гарантировано'),
		('likely', 'Вероятно'),
		('planned', 'Запланировано'),
	)
	contract = models.ForeignKey('ProjectContract.Contract', on_delete=models.CASCADE,
	                             related_name='cashflow_entries', verbose_name='Договор')
	payment = models.ForeignKey('ProjectContract.ContractPayments', on_delete=models.CASCADE,
	                            related_name='cashflow_entries', verbose_name='Платёж')
	date = models.DateField(verbose_name='Дата')
	amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Сумма')
	bucket = models.CharField(max_length=20, choices=BUCKETS, verbose_name='Корзина')

	class Meta:
		verbose_name = 'Строка ДДС'
		verbose_name_plural = 'ДДС (материализованное)'
		ordering = ['date', 'id']
		indexes = [models.Index(fields=['contract', 'date']),
		           models.Index(fields=['bucket', 'date'])]

	def __str__(self):
		return f'{self.date} {self.get_bucket_display()} {self.amount}'


class PaymentTaskLink(BaseModel):
    """Связь платёж ↔ работа (TaskNode) — DMC-2.

    Привязывает сумму платежа к конкретной задаче для отслеживания
    «сколько работ выполнено vs оплачено».
    Валидация: amount_applied <= task_node.price и <= остаток по договору.
    """
    payment = models.ForeignKey(
        'ProjectContract.ContractPayments',
        on_delete=models.CASCADE,
        related_name='task_links',
        verbose_name='Платёж',
    )
    task_node = models.ForeignKey(
        'ProjectTDL.TaskNode',
        on_delete=models.CASCADE,
        related_name='payment_links',
        verbose_name='Задача (TaskNode)',
    )
    amount_applied = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name='Применённая сумма',
        help_text='Сумма платежа, привязанная к этой задаче',
    )
    notes = models.TextField(
        null=True, blank=True,
        verbose_name='Примечания',
    )

    class Meta:
        verbose_name = 'Привязка платёж ↔ задача'
        verbose_name_plural = 'Привязки платёж ↔ задача'
        unique_together = ('payment', 'task_node')
        ordering = ['id']

    def __str__(self):
        return f'{self.payment} → {self.task_node} ({self.amount_applied})'

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.amount_applied is not None and self.amount_applied < 0:
            raise ValidationError('Сумма не может быть отрицательной.')
        if self.task_node_id and self.amount_applied:
            total_other = PaymentTaskLink.objects.filter(
                task_node=self.task_node
            ).exclude(pk=self.pk).aggregate(
                total=Sum('amount_applied')
)['total'] or Decimal('0')
            new_total = total_other + self.amount_applied
            task_price = self.task_node.price or Decimal('0')
            if new_total > task_price:
                raise ValidationError(
                    f'Сумма привязок ({new_total}) превышает '
                    f'стоимость задачи ({task_price}).'
                )
            concept = EstimateConcept.objects.filter(task_node=self.task_node).first()
            if concept is not None and new_total > (concept.amount or Decimal('0')):
                raise ValidationError(
                    f'Сумма привязок ({new_total}) превышает '
                    f'позицию сметы ({concept.amount}).'
                )
        if self.payment_id and self.amount_applied:
            contract = self.payment.contract
            total_contract_links = PaymentTaskLink.objects.filter(
                payment__contract=contract
            ).exclude(pk=self.pk).aggregate(
                total=Sum('amount_applied')
            )['total'] or Decimal('0')
            contract_total_paid = total_contract_links + self.amount_applied
            contract_price = contract.price or Decimal('0')
            if contract_total_paid > contract_price:
                raise ValidationError(
                    f'Сумма привязок по договору ({contract_total_paid}) '
                    f'превышает стоимость договора ({contract_price}).'
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ContractEstimate(BaseModel):
    """Смета договора — DMC-3.

    Связующее звено между объёмами работ (EstimateConcept) и деньгами.
    total_amount пересчитывается через rollup(): sum(concepts.amount).
    """
    ESTIMATE_STATUS = (
        ('draft', 'Черновик'),
        ('approved', 'Утверждена'),
    )
    contract = models.ForeignKey(
        'ProjectContract.Contract',
        on_delete=models.CASCADE,
        related_name='estimates',
        verbose_name='Договор',
    )
    name = models.CharField(max_length=200, verbose_name='Наименование')
    status = models.CharField(max_length=20, choices=ESTIMATE_STATUS,
                              default='draft', verbose_name='Статус')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                       verbose_name='Итоговая сумма')

    class Meta:
        verbose_name = 'Смета'
        verbose_name_plural = 'Сметы'
        ordering = ['id']

    def __str__(self):
        return f'{self.name} ({self.contract})'

    @property
    def rollup_amount(self):
        """Сумма позиций сметы (EstimateConcept.amount) без сохранения."""
        agg = self.concepts.aggregate(total=Sum('amount'))
        return agg['total'] or Decimal('0')

    def rollup(self):
        """Пересчитать sum(EstimateConcept.amount) и сохранить в total_amount."""
        self.total_amount = self.rollup_amount
        self.save(update_fields=['total_amount', 'update_stamp'])
        return self.total_amount

    @property
    def is_overrun(self):
        """Flag перерасхода: сумма позиций > цена договора."""
        return self.rollup_amount > (self.contract.price or Decimal('0'))


class EstimateConcept(BaseModel):
    """Позиция сметы: объём x цена = сумма (DMC-3).

    task_node FK — привязка к конкретной работе TaskNode.
    """
    estimate = models.ForeignKey(
        'ProjectContract.ContractEstimate',
        on_delete=models.CASCADE,
        related_name='concepts',
        verbose_name='Смета',
    )
    name = models.CharField(max_length=200, verbose_name='Наименование')
    unit = models.CharField(max_length=50, null=True, blank=True, verbose_name='Ед. изм.')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                   verbose_name='Объём')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                     verbose_name='Цена за ед.')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                 verbose_name='Сумма')
    task_node = models.ForeignKey(
        'ProjectTDL.TaskNode',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='estimate_concepts',
        verbose_name='Задача (TaskNode)',
    )

    class Meta:
        verbose_name = 'Позиция сметы'
        verbose_name_plural = 'Позиции сметы'
        ordering = ['id']

    def __str__(self):
        return f'{self.name} ({self.amount})'

    def save(self, *args, **kwargs):
        if self.quantity is not None and self.unit_price is not None:
            self.amount = Decimal(self.quantity) * Decimal(self.unit_price)
        super().save(*args, **kwargs)
        if self.estimate_id:
            self.estimate.rollup()


class TaskComment(BaseModel):
    """Комментарий к задаче (DMX-3, C8).

    Минимальный v1: текст + автор + дата (creation_stamp от BaseModel).
    Запись в ContractChangeLog (task:comment) — в вьюхе, не в сигнале
    (автоматика при bulk не нужна).
    """
    task = models.ForeignKey('ProjectTDL.TaskNode', null=True, blank=True,
                             on_delete=models.SET_NULL, related_name='comments',
                             verbose_name='Задача')
    author = models.ForeignKey('auth.User', null=True, blank=True,
                               on_delete=models.SET_NULL, related_name='task_comments',
                               verbose_name='Автор')
    body = models.TextField(verbose_name='Текст комментария')

    class Meta:
        verbose_name = 'Комментарий к задаче'
        verbose_name_plural = 'Комментарии к задачам'
        ordering = ['-creation_stamp', '-id']

    def __str__(self):
        target = self.task
        author = self.author
        return f'{self.creation_stamp:%d.%m.%Y %H:%M} {author}: «{target}»'


class Tag(BaseModel):
    """Унифицированный тег (DMX-4, C10).

    Общий для задач, договоров, писем. email_ui использует свой EmailTag —
    миграция на единый Tag отдельной карточкой; пока Tag работает параллельно.
    """
    name = models.CharField(max_length=100, unique=True, verbose_name='Тег')
    color = models.CharField(max_length=7, default='#6c757d',
                             verbose_name='Цвет (hex)')
    description = models.CharField(max_length=255, blank=True, default='',
                                   verbose_name='Описание')

    class Meta:
        verbose_name = 'Тег'
        verbose_name_plural = 'Теги'
        ordering = ['name']

    def __str__(self):
        return self.name


class TaggedItem(BaseModel):
    """Связь тег ↔ объект (DMX-4, C10).

    Через contenttype/object_id — универсальная привязка к любой модели.
    """
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE,
                            related_name='tagged_items',
                            verbose_name='Тег')
    content_type = models.ForeignKey('contenttypes.ContentType',
                                     on_delete=models.CASCADE,
                                     verbose_name='Тип объекта')
    object_id = models.PositiveBigIntegerField(verbose_name='ID объекта')
    created_by = models.ForeignKey('auth.User', null=True, blank=True,
                                   on_delete=models.SET_NULL,
                                   verbose_name='Кто привязал')

    class Meta:
        verbose_name = 'Привязка тега'
        verbose_name_plural = 'Привязки тегов'
        unique_together = [('tag', 'content_type', 'object_id')]

    def __str__(self):
        return f'{self.tag} → {self.content_type} #{self.object_id}'


class Attachment(BaseModel):
    """Файл на задаче/договоре (DMX-4, C11).

    MEDIA_ROOT = e:\\Проекты Симрус\\Переписка. Связи SET_NULL —
    файл переживает удаление объекта.
    """
    file = models.FileField(upload_to='attachments/%Y/%m/',
                            verbose_name='Файл')
    task = models.ForeignKey('ProjectTDL.TaskNode', null=True, blank=True,
                             on_delete=models.SET_NULL, related_name='attachments',
                             verbose_name='Задача')
    contract = models.ForeignKey('Contract', null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name='attachments',
                                 verbose_name='Договор')
    uploaded_by = models.ForeignKey('auth.User', null=True, blank=True,
                                    on_delete=models.SET_NULL,
                                    verbose_name='Загрузил')
    description = models.CharField(max_length=255, blank=True, default='',
                                   verbose_name='Описание')

    class Meta:
        verbose_name = 'Файл'
        verbose_name_plural = 'Файлы'
        ordering = ['-creation_stamp', '-id']

    def __str__(self):
        name = self.file.name.split('/')[-1] if self.file else '—'
        target = self.task or self.contract
        return f'{name} → {target}'
