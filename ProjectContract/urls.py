from django.urls import path
from ProjectContract import views

urlpatterns = [
    path("dashboard/", views.contract_dashboard, name='contract_dashboard'),
    path("payment/<int:pk>/toggle/", views.toggle_payment, name='toggle_payment'),
    path("payments_gantt/", views.payments_gantt, name='payments_gantt'),
    path('export-contracts/', views.export_contracts_excel, name='export_contracts_excel'),
    path('contract-payment-add/', views.contract_payment_add_edit, name='contract_payment_add'),
    path('contract-payment-edit/<int:payment_id>/', views.contract_payment_add_edit, name='contract_payment_change'),
    path('contract-payment-delete/<int:payment_id>/', views.contract_payment_delete, name='contract_payment_delete'),
    path('duplicate-contractpayment/<int:pk>/', views.duplicate_contractpayment, name='duplicate-contractpayment'),
]