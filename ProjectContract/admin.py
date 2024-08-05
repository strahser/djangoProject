import numpy as np
from django.contrib.humanize.templatetags import humanize
from django.contrib import admin
from django.utils.safestring import mark_safe
import pandas as pd
from django_pandas.io import read_frame
from AdminUtils import get_standard_display_list, duplicate_event
from ProjectContract.models import PaymentCalendar, Contract, ConcretePaymentCalendar, ContractPayments
from services.DataFrameRender.RenderDfFromModel import PIVOT_HTML_PROPERTY, renamed_dict
from django.db.models import Sum, F


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
        'contract__name': 'Договор',
        'contract__contractpayments__name': 'Платеж',
        'date': 'Дата',
        'payment_value': 'Стоимость'
    }

    @classmethod
    def create_pivot_html_table(cls, calendar_data: pd.DataFrame) -> str:
        pivot_table = calendar_data.pivot_table(**cls.pivot_data)
        pivot_table = pivot_table.applymap(lambda x: humanize.intcomma(x).replace(',', ' '))
        pivot_table.columns = pivot_table.columns.map(lambda x: cls.pivot_column_names.get(x, x))
        pivot_table.index.names = [cls.pivot_column_names.get(name, name) for name in pivot_table.index.names]
        pivot_table = pivot_table.fillna('')
        return pivot_table.to_html(**cls.html_data).replace('nan', '')


def create_payment_calendar(extra_context: dict, scale, all_contracts=None):
    all_contracts = all_contracts if all_contracts else Contract.objects.all()
    calendar_data = pd.DataFrame()  # Generate the Base payment calendar
    schedule_data = pd.DataFrame()  # Generate the detail payment schedule
    for contract in all_contracts:
        calendar_data = pd.concat([calendar_data,
                                   PaymentCalendar.generate_calendar(contract, scale=scale)],
                                  ignore_index=True)
        schedule_data = pd.concat([schedule_data,
                                   PaymentCalendar.generate_payment_schedule(contract, scale=scale)],
                                  ignore_index=True)
    # Добавьте код для отображения таблицы в шаблоне admin
    extra_context['calendar_table'] = mark_safe(PivotTableConfig.create_pivot_html_table(calendar_data))
    extra_context['schedule_table'] = mark_safe(PivotTableConfig.create_pivot_html_table(schedule_data))
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


class ContractPaymentsInline(admin.TabularInline):
    model = ContractPayments
    extra = 0


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    excluding_list = ['id', 'start_date', 'due_date', 'duration']
    list_display = get_standard_display_list(Contract, excluding_list=excluding_list)
    list_filter = get_standard_display_list(Contract, excluding_list=['id', 'proposal_number', 'price', 'name'])
    actions = [duplicate_event]
    inlines = (ContractPaymentsInline,)
    change_list_template = 'jazzmin/admin/change_list_contract.html'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        response = super().changelist_view(
            request,
            extra_context=extra_context,
        )
        scale = request.POST.get('scale', 'day')
        try:
            qs = response.context_data['cl'].queryset
            total_payments = get_contract_payments_status(qs)
        except (AttributeError, KeyError):
            return response
        agg_fields = ['total_payments', 'completed_payments', 'incomplete_payments']
        pivot_rows = ['contractor', 'name']
        values = agg_fields + ['price']
        try:
            _renamed_dict = renamed_dict(Contract)
            df = read_frame(qs)
            df1 = read_frame(total_payments)
            df1 = df1.groupby('contract__id', as_index=False)[agg_fields].agg(sum)
            df = df.merge(df1, left_on='id', right_on='contract__id', how='left')
            df_total = df['price'].sum()  # итого по договорам
            df_pivot = df.pivot_table(index=pivot_rows,
                                      values=values,
                                      aggfunc=np.sum,
                                      margins=True,
                                      margins_name='Итого'
                                      )

            df_html = (
                df_pivot
                .applymap(lambda x: humanize.intcomma(x).replace(',', ' '))
                .rename(_renamed_dict, axis='columns')
                .rename_axis(index=_renamed_dict)
                .to_html(**PIVOT_HTML_PROPERTY)
            )
            extra_context['pivot_table'] = df_html
            extra_context['df_total'] = df_total
        except Exception as e:
            print("Создание сводной таблицы Contract.changelist_view", e)
        payments = create_payment_calendar(extra_context, scale, qs)
        extra_context.update(payments)

        return super().changelist_view(request, extra_context=extra_context)  # return response in original


@admin.register(ConcretePaymentCalendar)
class PaymentCalendarAdmin(admin.ModelAdmin):
    change_list_template = 'jazzmin/admin/paymentCalendar.html'

    def changelist_view(self, request, extra_context=None):
        scale = request.POST.get('scale', 'day')
        extra_context = extra_context or {}
        payments = create_payment_calendar(extra_context, scale)
        extra_context.update(payments)
        return super().changelist_view(request, extra_context=extra_context)
