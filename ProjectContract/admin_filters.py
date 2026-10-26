# -*- coding: utf-8 -*-
"""P2: админ-фильтры ProjectContract (вынесено из admin.py 1:1).

Простые SimpleListFilter (подрядчик/договор/тип оплаты/проект),
хелпер _extract_scale и каскадные мультиселекты смет/позиций/актов.
Поведение, шаблоны и параметры URL не менялись.
"""
from django.contrib import admin
from django.db import models
from django.utils.translation import gettext_lazy as _

from ProjectContract.models import (
    Act, Contract, ContractEstimate, ContractPayments, Contractor,
    EstimateConcept,
)
from StaticData.models import ProjectSite


def _extract_scale(request):
    """Забрать scale из GET, чтобы админ не считал его lookup-фильтром (?e=1).

    Возвращает (scale, original_get). После super().changelist_view()
    нужно вернуть request.GET обратно, чтобы шаблоны видели полный querystring.
    """
    original = request.GET
    params = original.copy()
    scale = params.pop('scale', ['day'])[0]
    request.GET = params
    return scale, original


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


class MultiSelectFilterMixin:
    """Мультиселект для SimpleListFilter: ?contract=73&contract=74.

    Значения берутся из request.GET.getlist, в шаблоне — чекбоксы
    (templates/admin/multi_select_filter.html).
    """
    template = 'admin/multi_select_filter.html'
    lookup_arg = None  # например 'estimate__contract__in'

    def value(self):
        return [v for v in self.request.GET.getlist(self.parameter_name) if v]

    def queryset(self, request, queryset):
        vals = self.value()
        if vals:
            return queryset.filter(**{self.lookup_arg: vals})
        return queryset

    def choices(self, changelist):
        vals = set(self.value())
        yield {
            'selected': not vals,
            'query_string': changelist.get_query_string(remove=[self.parameter_name]),
            'display': _('Все'),
            'value': '',
            'is_all': True,
        }
        for lookup, title in self.lookup_choices:
            yield {
                'selected': str(lookup) in vals,
                'value': lookup,
                'display': title,
                'is_all': False,
            }


class EstimateContractorFilter(MultiSelectFilterMixin, admin.SimpleListFilter):
    """Подрядчик -> сужает договоры и сметы (каскад)."""
    title = 'Подрядчик'
    parameter_name = 'contractor'
    lookup_arg = 'contract__contractor__in'

    def lookups(self, request, model_admin):
        ids = ContractEstimate.objects.values_list('contract__contractor', flat=True).distinct()
        contractors = Contractor.objects.filter(id__in=ids).order_by('name')
        return [(str(c.id), str(c)) for c in contractors]


class EstimateContractFilter(MultiSelectFilterMixin, admin.SimpleListFilter):
    """Договор (только выбранного подрядчика)."""
    title = 'Договор'
    parameter_name = 'contract'
    lookup_arg = 'contract__in'

    def lookups(self, request, model_admin):
        contracts = Contract.objects.all().order_by('name')
        contractors = [v for v in request.GET.getlist('contractor') if v]
        if contractors:
            contracts = contracts.filter(contractor__in=contractors)
        contracts = contracts.filter(estimates__isnull=False).distinct()
        return [(str(c.id), str(c)) for c in contracts]


class ConceptContractorFilter(MultiSelectFilterMixin, admin.SimpleListFilter):
    """Подрядчик -> сужает договоры и сметы (каскад)."""
    title = 'Подрядчик'
    parameter_name = 'contractor'
    lookup_arg = 'estimate__contract__contractor__in'

    def lookups(self, request, model_admin):
        ids = EstimateConcept.objects.values_list('estimate__contract__contractor', flat=True).distinct()
        contractors = Contractor.objects.filter(id__in=ids).order_by('name')
        return [(str(c.id), str(c)) for c in contractors]


class ConceptContractFilter(MultiSelectFilterMixin, admin.SimpleListFilter):
    """Договор (только выбранного подрядчика)."""
    title = 'Договор'
    parameter_name = 'contract'
    lookup_arg = 'estimate__contract__in'

    def lookups(self, request, model_admin):
        contracts = Contract.objects.all().order_by('name')
        contractors = [v for v in request.GET.getlist('contractor') if v]
        if contractors:
            contracts = contracts.filter(contractor__in=contractors)
        contracts = contracts.filter(estimates__concepts__isnull=False).distinct()
        return [(str(c.id), str(c)) for c in contracts]


class ConceptEstimateFilter(MultiSelectFilterMixin, admin.SimpleListFilter):
    """Смета (только выбранного договора/подрядчика)."""
    title = 'Смета'
    parameter_name = 'estimate'
    lookup_arg = 'estimate__in'

    def lookups(self, request, model_admin):
        estimates = ContractEstimate.objects.all().order_by('name')
        contractors = [v for v in request.GET.getlist('contractor') if v]
        contracts = [v for v in request.GET.getlist('contract') if v]
        if contractors:
            estimates = estimates.filter(contract__contractor__in=contractors)
        if contracts:
            estimates = estimates.filter(contract__in=contracts)
        return [(str(e.id), f'{e.name} ({e.contract})') for e in estimates]


class ConceptActFilter(MultiSelectFilterMixin, admin.SimpleListFilter):
    """Акт закрытия (мультиселект + пункт «без акта»)."""
    title = 'Акт'
    parameter_name = 'act'
    lookup_arg = 'act__in'
    none_value = '__none__'
    none_display = 'Без акта'

    def lookups(self, request, model_admin):
        acts = Act.objects.select_related('contract').order_by(
            'contract__name', 'act_date', 'number')
        return [(self.none_value, self.none_display)] + [
            (str(a.id), str(a)) for a in acts]

    def queryset(self, request, queryset):
        vals = self.value()
        if not vals:
            return queryset
        q = models.Q()
        ids = [v for v in vals if v != self.none_value]
        if ids:
            q |= models.Q(**{self.lookup_arg: ids})
        if self.none_value in vals:
            q |= models.Q(act__isnull=True)
        return queryset.filter(q) if q else queryset
