from pandas.core.groupby import DataFrameGroupBy

from ProjectContract.models import ContractPayments, Contract, PaymentCalendar
from services.DataFrameRender.RenderDfFromModel import PIVOT_HTML_PROPERTY, renamed_dict
from django.db.models import Sum, F
from django.utils.safestring import mark_safe
import pandas as pd
from django_pandas.io import read_frame
import sys
from django.forms import Textarea

from loguru import logger

logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")
import numpy as np
from django.contrib.humanize.templatetags import humanize


def get_pivot_table_all_contracts(qs: ContractPayments.objects = None):
	"""
    Создает сводную таблицу по статусу платежа (made_payment) для всех контрактов,
    используя pandas.

    Returns:
        Pandas DataFrame с данными сводной таблицы.
    """
	qs = qs if qs else ContractPayments.objects
	payments_data = qs.values(
		'contract__id',
		'contract__name',  # Добавляем имя контракта
		'payment_type',
		'made_payment',
		'price',
		'contract__project_site__name',
		'contract__contractor__name',
	)

	df = pd.DataFrame(payments_data)
	payment_type_mapping = dict(ContractPayments.PAYMENT_TYPES)  # Получаем значения из модели
	df['payment_type'] = df['payment_type'].map(payment_type_mapping)
	pivot_table = pd.pivot_table(
		df,
		values='price',
		index=['contract__project_site__name', 'contract__contractor__name', 'contract__name', 'payment_type'],
		columns='made_payment',
		aggfunc='sum',
		fill_value=0,
		margins=True,
		margins_name='Итого'  # Name the total row/column
	)
	pivot_table = pivot_table.map(lambda x: humanize.intcomma(x).replace(',', ' '))
	pivot_table.index.names = [PivotTableConfig.pivot_column_names.get(name, name) for name in pivot_table.index.names]
	pivot_table.columns = pivot_table.columns.map(lambda x: PivotTableConfig.pivot_column_names.get(x, x))
	pivot_table = pivot_table.fillna('')
	return pivot_table


class PivotTableConfig:
	html_data = dict(
		index=True,
		border=1,  # Добавляем рамку таблицы
		classes='table table-bordered',  # Добавляем Bootstrap-стили
		col_space='150px',  # Увеличиваем ширину столбцов
		justify='center',  # Выравниваем текст по центру
		float_format='{:,.2f}'.format,  # Форматируем числа с разделителем тысяч и двумя знаками после запятой,
		na_rep='',
		escape=False,  # Отключаем экранирование HTML-тегов)
	)
	pivot_data = dict(
		index=['contract__name', 'contract__contractpayments__name'],
		columns='date',
		values='payment_value',
		aggfunc='sum',  # Use 'sum' for aggregation
		margins=True,  # Include totals
		margins_name='Итого'  # Name the total row/column
	)

	# Rename columns and index
	pivot_column_names = {
		'contract__project_site__name': 'Проект',
		'contract__name': 'Договор',
		'contract__contractpayments__name': 'Платеж',
		'date': 'Дата',
		'payment_value': 'Стоимость',
		'contract__id': 'id',
		'made_payment': "Статус Платежа",
		"payment_type": "Тип платежа",
		"True": "Оплачено",
		"False": "Не Оплачено",
		'contract__contractor__name': 'Подрядчик'

	}

	@classmethod
	def create_pivot_html_table(cls, calendar_data: pd.DataFrame) -> str:
		pivot_table = calendar_data.pivot_table(**cls.pivot_data)
		pivot_table = pivot_table.map(lambda x: humanize.intcomma(x).replace(',', ' '))
		pivot_table.columns = pivot_table.columns.map(lambda x: cls.pivot_column_names.get(x, x))
		pivot_table.index.names = [cls.pivot_column_names.get(name, name) for name in pivot_table.index.names]
		pivot_table = pivot_table.fillna('')
		return pivot_table.to_html(**cls.html_data).replace('nan', '')


def create_payment_calendar(extra_context: dict, scale, all_contracts=None,
                            contract_payment_filter: ContractPayments.objects = None) -> dict:
	all_contracts = all_contracts if all_contracts else Contract.objects.all()
	calendar_data = pd.DataFrame()  # Generate the Base payment calendar
	schedule_data = pd.DataFrame()  # Generate the detail payment schedule
	for contract in all_contracts:
		generated_calendar = PaymentCalendar.generate_calendar(contract, scale, contract_payment_filter)
		generated_payment_schedule = PaymentCalendar.generate_payment_schedule(contract, scale=scale)
		calendar_data = pd.concat([calendar_data, generated_calendar], ignore_index=True)
		schedule_data = pd.concat([schedule_data, generated_payment_schedule], ignore_index=True)
	# Добавьте код для отображения таблицы в шаблоне admin

	pivot_html = get_pivot_table_all_contracts(contract_payment_filter)\
				  .to_html(**PivotTableConfig.html_data)
	for k, v in PivotTableConfig.pivot_column_names.items():
		pivot_html = pivot_html.replace(k, v)
	extra_context['calendar_table'] = mark_safe(PivotTableConfig.create_pivot_html_table(calendar_data))
	extra_context['schedule_table'] = mark_safe(PivotTableConfig.create_pivot_html_table(schedule_data))
	extra_context['pivot_table'] = mark_safe(pivot_html)
	return extra_context


def get_contract_payments_status(contracts):
	# Фильтруем платежи по контрактам
	contract_payments = (ContractPayments.objects
	                     .filter(contract__in=contracts)
	                     .select_related('contract__id', 'contract__name', 'contract__price')
	                     .values('contract__id', 'name', 'price')
	                     .all())

	# Агрегируем информацию о платежах по контрактам
	payments_info = contract_payments \
		.annotate(
		total_payments=Sum('price'),
		completed_payments=Sum('price', filter=F('made_payment')),
		incomplete_payments=Sum('price', filter=~F('made_payment'))
	)

	# Добавляем информацию о платежах к каждому контракту
	return payments_info


def create_calendar_list_view(request, response, extra_context):
	scale = request.POST.get('scale', 'day')
	try:
		qs = response.context_data['cl'].queryset
		total_payments = get_contract_payments_status(qs)
	except Exception as e:
		logger.error(f"Ошибка Создание get_contract_payments_status  {e}")
		return response
	agg_fields = ['total_payments', 'completed_payments', 'incomplete_payments']
	pivot_rows = ['contractor', 'name']
	values = agg_fields + ['price']
	try:
		_renamed_dict = renamed_dict(Contract)
		df = read_frame(qs)
		df1 = read_frame(total_payments)
		df1 = df1.groupby('contract__id', as_index=False)[agg_fields].agg(DataFrameGroupBy.sum)
		df = df.merge(df1, left_on='id', right_on='contract__id', how='left')
		df_total = df['price'].DataFrameGroupBy.sum()  # итого по договорам
		# 1. Создание основной сводной таблицы с общими итогами.
		df_pivot = df.pivot_table(index=pivot_rows,
								  values=values,
								  aggfunc=DataFrameGroupBy.sum,
								  margins=True,
								  margins_name='Итого'
								  )
		df_html = (
			df_pivot
			.DataFrame.map (lambda x: humanize.intcomma(x).replace(',', ' '))
			.rename(_renamed_dict, axis='columns')
			.rename_axis(index=_renamed_dict)
			.to_html(**PIVOT_HTML_PROPERTY)
		)
		extra_context['pivot_table'] = df_html
		extra_context['df_total'] = df_total
	except Exception as e:
		logger.error(f"Ошибка Создание сводной таблицы Contract.changelist_view{e}")
	payments = create_payment_calendar(extra_context, scale, qs)
	extra_context.update(payments)
	return extra_context
