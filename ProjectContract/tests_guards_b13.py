# -*- coding: utf-8 -*-
"""Блок 13: гарды пустых выборок пивотов (прод-ошибки 2026-10-06 13:50).

KeyError 'contract__id' / 'payment_value' при договорах без платежей —
штатное состояние, а не ошибка: должны быть заглушки без ERROR-логов.
"""
from decimal import Decimal

from django.test import RequestFactory, TestCase

from ProjectContract.models import Contract, Contractor
from ProjectContract.PivotTableUtility import (
    create_calendar_list_view,
    create_payment_calendar,
    get_contract_payments_status,
    get_pivot_table_all_contracts,
)
from ProjectContract.PivotTableUtility import PivotTableConfig
from StaticData.models import ProjectSite


class PivotGuardsFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.site = ProjectSite.objects.create(name='B13-Объект')
        cls.contractor = Contractor.objects.create(name='B13-Подрядчик')
        cls.contract = Contract.objects.create(
            project_site=cls.site, contractor=cls.contractor,
            name='B13-Договор', price=Decimal('1000.00'))
        cls.rf = RequestFactory()


class EmptyPivotTest(PivotGuardsFixtureMixin, TestCase):
    def test_all_contracts_empty_frame(self):
        from ProjectContract.models import ContractPayments
        df = get_pivot_table_all_contracts(
            ContractPayments.objects.filter(contract=self.contract))
        self.assertTrue(df.empty)

    def test_pivot_html_table_empty_returns_none(self):
        import pandas as pd
        # Блок 13: пустой фрейм — None (заглушку ставит вызывающий),
        # а не KeyError 'payment_value'.
        self.assertIsNone(
            PivotTableConfig.create_pivot_html_table(pd.DataFrame()))

    def test_payment_calendar_stubs_without_payments(self):
        out = create_payment_calendar({}, 'day')
        self.assertIn('Нет данных', out['calendar_table'])
        self.assertIn('Нет данных', out['schedule_table'])
        self.assertIn('Нет данных', out['pivot_table'])

    def test_list_view_stubs_without_payments(self):
        req = self.rf.get('/admin/')
        resp = type('R', (), {'context_data': {
            'cl': type('CL', (), {'queryset': Contract.objects.all()})()}})()
        out = create_calendar_list_view(req, resp, {})
        self.assertIn('Нет данных', out['pivot_table'])
        self.assertEqual(out['df_total'], 0)


class PaymentsStatusTest(PivotGuardsFixtureMixin, TestCase):
    def test_status_rows(self):
        from ProjectContract.models import ContractPayments
        ContractPayments.objects.create(
            contract=self.contract, name='P1',
            price=Decimal('300.00'), status='paid')
        rows = list(get_contract_payments_status(Contract.objects.all()))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['contract__id'], self.contract.pk)
        self.assertEqual(rows[0]['total_payments'], Decimal('300'))
