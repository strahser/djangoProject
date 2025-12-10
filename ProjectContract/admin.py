import sys

import pandas as pd
from django.contrib import admin, messages

from django.forms import Textarea
from django_pandas.io import read_frame

from AdminUtils import get_standard_display_list, duplicate_event, duplicate_object
from ProjectContract.PivotTableUtility import create_calendar_list_view, create_payment_calendar

from ProjectContract.form import ContractPaymentsAdminForm
from ProjectContract.models import ContractPayments, Contractor
from django.db import models
from django.db.models import Sum, Value, DecimalField, Count, Q
from django.db.models.functions import Coalesce
from django.db.models import F

from StaticData.models import ProjectSite
from .models import Contract  # Замените на свою модель
from django import forms
from loguru import logger
from django.http import HttpResponse
from django.utils.html import format_html
from urllib.parse import urlencode
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse, path
from django.utils.translation import gettext_lazy as _
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")


class ProjectSiteFilter(admin.SimpleListFilter):
    title = _('Project Site')
    parameter_name = 'project_site'

    def lookups(self, request, model_admin):
        project_sites = Contract.objects.values('project_site').distinct().order_by('project_site')
        return [(str(ProjectSite.objects.get(id=site['project_site']).id),
                 str(ProjectSite.objects.get(id=site['project_site']))) for site in project_sites]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(contract__project_site=self.value())
        return queryset


class ContractorFilter(admin.SimpleListFilter):
    title = _('Contractor')
    parameter_name = 'contractor'

    def lookups(self, request, model_admin):
        project_site = request.GET.get('project_site')
        contractors = Contract.objects.values('contractor').distinct().order_by('contractor')
        if project_site:
            contractors = contractors.filter(project_site=project_site)
        return [(str(Contractor.objects.get(id=contractor['contractor']).id),
                 str(Contractor.objects.get(id=contractor['contractor']))) for contractor in contractors]
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(contract__contractor=self.value())
        return queryset


class ContractFilter(admin.SimpleListFilter):
    title = _('Contract')
    parameter_name = 'contract'
    def lookups(self, request, model_admin):
        project_site = request.GET.get('project_site')
        contractor = request.GET.get('contractor')
        contracts = Contract.objects.all().order_by('name')
        if project_site:
           contracts = contracts.filter(project_site=project_site)
        if contractor:
           contracts = contracts.filter(contractor=contractor)
        return contracts.values_list('id', 'name')
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(contract=self.value())
        return queryset


class PaymentTypeFilter(admin.SimpleListFilter):
    title = _('Payment Type')
    parameter_name = 'payment_type'


    def lookups(self, request, model_admin):
        contract_filter = request.GET.get('contract')
        payment_types = ContractPayments.objects.values('payment_type').distinct().order_by('payment_type')
        if contract_filter:
            payment_types = payment_types.filter(contract=contract_filter)
        return [(str(payment['payment_type']),
                 str(ContractPayments.objects.filter(payment_type=payment['payment_type']).first().get_payment_type_display())) for payment in payment_types]


    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(payment_type=self.value())
        return queryset


def calculate_price(instance):
    if instance.use_custom_formula:
        try:
            # Вычислить результат формулы
            result = eval(instance.custom_formula)
            setattr(instance, instance.field_to_overwrite, result)
        except Exception as e:
            raise forms.ValidationError(f'Ошибка при выполнении формулы: {e}')


def export_as_excel_pandas(modeladmin, request, queryset):
    """
    Кастомное действие для экспорта данных в Excel с использованием pandas и django-pandas.
    """
    # Получаем отображаемые поля из list_display
    list_display = modeladmin.list_display

    # Аннотируем queryset нужными полями
    queryset = queryset.annotate(
        paid_amount=Coalesce(Sum('contractpayments__price', filter=Q(contractpayments__made_payment=True)), Value(0),
                             output_field=DecimalField(max_digits=12, decimal_places=2))
    ).annotate(
        unpaid_amount=Coalesce(Sum('contractpayments__price', filter=Q(contractpayments__made_payment=False)), Value(0),
                               output_field=DecimalField(max_digits=12, decimal_places=2))
    ).annotate(
        status_check=F('price') - (
                    Coalesce(Sum('contractpayments__price', filter=Q(contractpayments__made_payment=True)), Value(0),
                             output_field=DecimalField(max_digits=12, decimal_places=2)) + Coalesce(
                Sum('contractpayments__price', filter=Q(contractpayments__made_payment=False)), Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2)))
    )

    # Получаем verbose_name для полей
    verbose_names = {}
    for field_name in list_display:
        if hasattr(modeladmin, field_name):  # проверяем, если это функция, а не поле
            verbose_names[field_name] = getattr(modeladmin, field_name).short_description
        else:
            verbose_names[field_name] = modeladmin.model._meta.get_field(field_name).verbose_name

    # Создаем DataFrame, используя django-pandas
    df = read_frame(
        queryset,
        fieldnames=list_display,
    )

    # Переименовываем столбцы
    df.rename(columns=verbose_names, inplace=True)

    # Конвертируем Decimal и другие типы в float перед экспортом
    for column in df.columns:
        if df[column].dtype == 'object':
            try:
                df[column] = df[column].astype(float)
            except (ValueError, TypeError):
                pass  # Оставляем как есть, если не удается преобразовать

    # Создаем HTTP-ответ с Excel-файлом
    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = 'attachment; filename="contracts.xlsx"'

    # Сохраняем DataFrame в Excel
    df.to_excel(response, index=False,
                engine='openpyxl')  # engine='openpyxl' чтобы pandas использовал openpyxl, а не xlsxwriter

    return response

export_as_excel_pandas.short_description = "Скачать выбранные контракты в Excel (Pandas)"

class BaseAdmin(admin.ModelAdmin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_name = self.model._meta.app_label
        self.model_name = self.model._meta.model_name

    def actions_column(self, obj):
        return format_html(
            '<a class="button" href="{}" title="Дублировать">{}</a>',
            reverse(f'admin:duplicate-{self.model_name}', args=[obj.pk]),
            '📋'  # Unicode символ для копирования
        )
    actions_column.short_description = format_html(
         '{}', '☰'
        )

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
             path(
                 f'duplicate-{self.model_name}/<int:pk>/',
                self.duplicate_view,
                 name=f'duplicate-{self.model_name}'
             ),
        ]
        return my_urls + urls

    def duplicate_view(self, request, pk):
        obj = self.get_object(request, pk)
        duplicate_object(obj)
        return redirect(request.META.get('HTTP_REFERER', reverse(f'admin:{self.app_name}_{self.model_name}_changelist')))


class ContractPaymentsInline(admin.TabularInline):
    model = ContractPayments
    extra = 0
    readonly_fields = ( 'edit_link','duplicate_button')
    fields = ('name', 'payment_type', 'price','percent','made_payment', 'edit_link','duplicate_button')

    def duplicate_button(self, obj):
         if obj and obj.pk: # Проверка что обьект существует и есть pk.
            return format_html(
                '<a href="{}" title="Дублировать">&#128203;</a>',
                reverse('duplicate-contractpayment', args=[obj.pk])
            )
         else:
             return ""
    duplicate_button.short_description = "Дублировать"


    def add_payment_button(self, obj):
        contract_id = obj.pk if obj else None
        add_url = reverse('admin:ProjectContract_contractpayments_add')
        add_url = f"{add_url}?{urlencode({'contract': contract_id, '_next': reverse('admin:ProjectContract_contract_change', args=[contract_id])})}"
        return format_html(
            '<div style="margin-bottom: 10px;"><a class="button" href="{}">Добавить платеж</a></div>',
            add_url
        )
    def edit_link(self, obj):
        if obj and obj.pk:
            contract_id = obj.contract_id
            base_url = reverse('admin:ProjectContract_contractpayments_change', args=[obj.pk])
            edit_url = f"{base_url}?{urlencode({'_next': reverse('admin:ProjectContract_contract_change', args=[contract_id])})}"
            return format_html(
                '<a href="{}" class="button">✏️</a>',
                edit_url
            )
        return format_html(
            '<span style="color: gray;">Нет платежа</span>'
        )

    edit_link.short_description = "☰"


@admin.register(Contract)
class ContractAdmin(BaseAdmin):
    app_name = "ProjectContract"
    excluding_list = ['start_date', 'due_date', 'duration', 'proposal_link']
    additional_list =['paid_amount','unpaid_amount','status_check','actions_column']
    list_display = get_standard_display_list(Contract, excluding_list=excluding_list,additional_list=additional_list)
    list_filter = get_standard_display_list(Contract, excluding_list=['id', 'proposal_number', 'price', 'name'])
    actions = [duplicate_event]
    inlines = (ContractPaymentsInline,)
    change_list_template = 'jazzmin/admin/change_list_contract.html'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        response = super().changelist_view(request,extra_context=extra_context)
        _extra_context = create_calendar_list_view(request, response, extra_context)
        try:
            if hasattr(response,"context_data"):
                # Получаем queryset
                qs = response.context_data["cl"].queryset
                # Вычисляем суммы
                total_price = qs.aggregate(total=Sum('price'))['total']
                total_paid = qs.aggregate(total=Coalesce(Sum('contractpayments__price', filter=models.
                                                             Q(contractpayments__made_payment=True)), Value(0),
                                                                output_field=DecimalField(max_digits=12, decimal_places=2)))['total']
                total_unpaid = qs.aggregate(total=Coalesce(Sum('contractpayments__price', filter=models.
                                                               Q(contractpayments__made_payment=False)), Value(0),
                                                                output_field=DecimalField(max_digits=12, decimal_places=2)))['total']

                 # Добавляем итоговые значения в контекст
                _extra_context['total_price'] = total_price
                _extra_context['total_paid'] = total_paid
                _extra_context['total_unpaid'] = total_unpaid
                _extra_context['total_status'] = total_price-(total_paid+total_unpaid)

        except KeyError:
            pass
        return super().changelist_view(request, extra_context=extra_context)  # return response in original

    def paid_amount(self, obj):
      return obj.contractpayments_set.filter(made_payment=True)\
      .aggregate(total=Coalesce(Sum('price'),Value(0), output_field=DecimalField(max_digits=12,decimal_places=2)))['total']

    def unpaid_amount(self, obj):
      return obj.contractpayments_set.filter(made_payment=False)\
      .aggregate(total=Coalesce(Sum('price'),Value(0), output_field=DecimalField(max_digits=12,decimal_places=2)))['total']

    def status_check(self, obj):
      return obj.price - (self.paid_amount(obj) + self.unpaid_amount(obj))


    paid_amount.short_description = 'Оплаченная сумма'
    unpaid_amount.short_description = 'Неоплаченная сумма'
    status_check.short_description = 'Статус проверки'


@admin.register(ContractPayments)
class ContractPaymentsAdmin(admin.ModelAdmin):
    _all_list = ['contract',  'price', 'start_date', 'due_date', 'duration']
    list_display = ['id', 'parent', 'project_site', 'payment_type', 'made_payment', 'contractor_name', ] + _all_list
    list_filter = [ContractFilter, ProjectSiteFilter,ContractorFilter, PaymentTypeFilter,  'made_payment','start_date']
    search_fields = ['contract__name', 'name']
    list_display_links = ['id', ]
    list_editable = ['parent', 'start_date', 'due_date', 'duration']
    actions = [duplicate_event,]
    form = ContractPaymentsAdminForm
    list_per_page = 10
    change_list_template = 'jazzmin/admin/paymentCalendar.html'

    formfield_overrides = {
        models.TextField: {
            'widget': Textarea(attrs={'cols': 60, 'rows': 2})
        },
    }


    def response_post_save_add(self, request, obj):
        next_url = request.GET.get('_next')
        if next_url:
            return HttpResponseRedirect(next_url)
        return super().response_post_save_add(request, obj)

    def response_post_save_change(self, request, obj):
        next_url = request.GET.get('_next')
        if next_url:
            return HttpResponseRedirect(next_url)
        return super().response_post_save_change(request, obj)

    def changelist_view(self, request, extra_context=None):
        scale = request.GET.get('scale', 'day')
        extra_context = extra_context or {}
        response = super().changelist_view(request, extra_context=extra_context)
        try:
            # Проверяем наличие context_data
            if hasattr(response, 'context_data'):
                qs = response.context_data['cl'].queryset
                qs = qs.filter()
                filtered_contracts = qs.values_list('contract', flat=True)
                contract_list = Contract.objects.filter(id__in=filtered_contracts).all()
                payments = create_payment_calendar(extra_context, scale, all_contracts=contract_list, contract_payment_filter=qs)
                extra_context.update(payments)
            else:
                # Получаем queryset другим способом, например, из request.session
                qs = request.session.get('queryset')

        except Exception as e:
            messages.error(request, f" ошибка {e}")

        return super().changelist_view(request, extra_context=extra_context)

    # После сохранения объекта
    def save_model(self, request, obj, form, change):
        calculate_price(obj)
        super().save_model(request, obj, form, change)

