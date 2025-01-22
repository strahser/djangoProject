import datetime
from decimal import Decimal

import pandas as pd
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.db.models import F, Sum, Max, Min, DateField
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
import gantt  # pip install python-gantt
from django.contrib import admin

from django.contrib.humanize.templatetags.humanize import intcomma
import datetime

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


class Contract(BaseModel):
	project_site = models.ForeignKey('StaticData.ProjectSite', verbose_name='Проект',
	                                 null=False,
	                                 on_delete=models.CASCADE
	                                 )
	sub_project = models.ForeignKey('StaticData.SubProject', verbose_name='Подпроект',
	                                null=True,
	                                blank=True,
	                                on_delete=models.DO_NOTHING,
	                                )
	contractor = models.ForeignKey('ProjectContract.Contractor', on_delete=models.CASCADE, verbose_name='Подрядчик')
	name = models.CharField(max_length=200, null=True, verbose_name='Описание')
	price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="цена договора", default=0)
	proposal_number = models.CharField(max_length=200, null=True, blank=True, verbose_name='Proposal')
	proposal_link = models.TextField(max_length=300, null=True, blank=True, verbose_name='Proposal link')
	start_date = models.DateField(verbose_name="план.начало", null=True, blank=True,default=datetime.date.today )
	duration = models.FloatField(verbose_name="длительность", null=True, blank=True, default=1)
	due_date = models.DateField(verbose_name="план.завершение", null=True, blank=True,default=datetime.date.today)

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
	name = models.CharField(max_length=200,null=True, verbose_name='Наименование платежа')
	payment_type = models.CharField(max_length=200, choices=PAYMENT_TYPES, default='advance',
	                                verbose_name='Тип платежа', null=True, blank=True)
	payment_description = models.TextField(verbose_name="Описание платежа", null=True, blank=True, )
	price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="цена", default=0)
	contract = models.ForeignKey('ProjectContract.Contract', on_delete=models.CASCADE, verbose_name='Договор')
	percent = models.FloatField(verbose_name="процент", null=True, blank=True, )
	parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children',
	                           verbose_name="Зависимость")
	made_payment = models.BooleanField(verbose_name='Оплачено?', default=False)
	custom_formula = models.CharField(max_length=255, blank=True, null=True)
	use_custom_formula = models.BooleanField(default=False, null=True)
	field_to_overwrite = models.CharField(max_length=255, null=True, blank=True,
	                                      choices=[('price', 'цена'), ])
	start_date = models.DateField(verbose_name="план.начало", null=True, blank=True,default=datetime.date.today )
	duration = models.FloatField(verbose_name="длительность", null=True, blank=True, default=1)
	due_date = models.DateField(verbose_name="план.завершение", null=True, blank=True,default=datetime.date.today)
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

	def generate_gantt_svg(self):
		"""
        Создает SVG-диаграмму Ганта для данной модели ContractPayments и ее дочерних платежей.
        """
		gantt_chart = gantt.Project(name="Платежи по договору")
		t1 = gantt.Task(name=self.name,
		                start=self.start_date,
		                duration=self.duration,
		                percent_done=50 if self.made_payment else 0,
		                color='lightgreen' if self.made_payment else 'red'
		                )
		gantt_chart.add_task(t1)

		# Добавление дочерних платежей
		for child in self.children.all():
			t1 = gantt.Task(name=child.name,
			                start=child.start_date,
			                duration=child.duration,
			                percent_done=50 if self.made_payment else 0,
			                color='lightgreen' if self.made_payment else 'red',
			                depends_of=self.name
			                )
			gantt_chart.add_task(t1)
		td = datetime.timedelta(days=self.duration)
		return gantt_chart.make_svg_for_tasks(
			filename='templates/gantt_chart.svg', start=self.start_date - td, end=self.due_date + td)

	def save(self, *args, **kwargs):
		# Если у платежа есть предшественник, используем его дату окончания
		self.formatted_number = intcomma(self.price)
		if self.percent and not self.use_custom_formula:
			self.price = self.percent * float(self.contract.price)
		if self.id:
			if self.parent:
				self.start_date = self.parent.due_date

			# Рассчитываем дату окончания
			if self.start_date and self.duration:
				self.due_date = self.start_date + timezone.timedelta(days=self.duration)

			# Обновляем даты начала и окончания для дочерних платежей
			self.update_children()
		super().save(*args, **kwargs)

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
        Рекурсивно обновляет даты начала и окончания для всех дочерних платежей.
        """
		for child in self.children.all():
			child.update_start_date()
			child.save()


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
		payments = ContractPayments.objects.filter(contract=contract)
		df_columns_data = {
			'start_date': [payment.start_date for payment in payments],
			'due_date': [payment.due_date for payment in payments],
			'payment_value': [float(payment.price) / (payment.duration if payment.duration > 0 else 1) for payment in
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
			dates = pd.date_range(start=row['start_date'], end=row['due_date'], periods=int(row['duration']))
			payment_dates.extend(dates.to_pydatetime())
			# Create a list of payment values for the duration (convert to int)
			payment_values.extend([float(row['payment_value'])] * int(row['duration']))
			# Add contract name for each payment
			contract_names.extend([row['contract__name']] * int(row['duration']))
			# Add payment name for each payment
			payment_names.extend([row['contract__contractpayments__name']] * int(row['duration']))
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
