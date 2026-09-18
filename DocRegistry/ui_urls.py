from django.urls import path

from . import views

urlpatterns = [
    path('<str:project>/queue/', views.queue_view, name='docs_queue'),
    path('<str:project>/revision/<int:pk>/', views.revision_view, name='docs_revision'),
    path('<str:project>/entry/<int:code>/', views.entry_view, name='docs_entry'),
    path('<str:project>/remark/<int:pk>/sheet.pdf', views.remark_sheet_pdf, name='docs_remark_sheet'),
    path('<str:project>/issue/<int:pk>/waybill.pdf', views.waybill_pdf, name='docs_waybill'),
    path('<str:project>/issue/<int:pk>/approval.pdf', views.approval_pdf, name='docs_approval'),
]
