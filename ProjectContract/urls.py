from django.urls import path
from ProjectContract import views

urlpatterns = [
    path("dashboard/", views.contract_dashboard, name='contract_dashboard'),
    path("<int:pk>/", views.contract_detail, name='contract_detail'),
    path("<int:pk>/tab/<str:tab>/", views.contract_tab, name='contract_tab'),
    path("help/", views.help_memo, name='contract_help'),
    path("cashflow/", views.cashflow, name='cashflow'),
    path("payment/<int:pk>/toggle/", views.toggle_payment, name='toggle_payment'),
    path("<int:pk>/remind/", views.contract_reminder_add, name='contract_reminder_add'),
    path("<int:pk>/attach/", views.contract_attachment_add, name='contract_attachment_add'),
    path("reminder/<int:pk>/toggle/", views.reminder_toggle, name='reminder_toggle'),
    path("payments_gantt/", views.payments_gantt, name='payments_gantt'),
    path('export-contracts/', views.export_contracts_excel, name='export_contracts_excel'),
    path('contract-payment-add/', views.contract_payment_add_edit, name='contract_payment_add'),
    path('contract-payment-edit/<int:payment_id>/', views.contract_payment_add_edit, name='contract_payment_change'),
    path('contract-payment-delete/<int:payment_id>/', views.contract_payment_delete, name='contract_payment_delete'),
    path('duplicate-contractpayment/<int:pk>/', views.duplicate_contractpayment, name='duplicate-contractpayment'),
]