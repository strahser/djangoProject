from django.urls import path
from ProjectContract import views, views_cashflow, views_dds, views_payments

urlpatterns = [
    path("dashboard/", views_cashflow.contract_dashboard, name='contract_dashboard'),
    path("<int:pk>/", views.contract_detail, name='contract_detail'),
    path("<int:pk>/tab/<str:tab>/", views.contract_tab, name='contract_tab'),
    path("help/", views_cashflow.help_memo, name='contract_help'),
    path("cashflow/", views_cashflow.cashflow, name='cashflow'),
    path("dds/", views_dds.dds_report, name='dds_report'),
    path("payment/<int:pk>/toggle/", views_payments.toggle_payment, name='toggle_payment'),
    path("<int:pk>/remind/", views.contract_reminder_add, name='contract_reminder_add'),
    path("<int:pk>/attach/", views.contract_attachment_add, name='contract_attachment_add'),
    path("reminder/<int:pk>/toggle/", views.reminder_toggle, name='reminder_toggle'),
    path("payments_gantt/", views_payments.payments_gantt, name='payments_gantt'),
    path('export-contracts/', views_payments.export_contracts_excel, name='export_contracts_excel'),
    path('contract-payment-add/', views_payments.contract_payment_add_edit, name='contract_payment_add'),
    path('contract-payment-edit/<int:payment_id>/', views_payments.contract_payment_add_edit, name='contract_payment_change'),
    path('contract-payment-delete/<int:payment_id>/', views_payments.contract_payment_delete, name='contract_payment_delete'),
    path('duplicate-contractpayment/<int:pk>/', views_payments.duplicate_contractpayment, name='duplicate-contractpayment'),
]