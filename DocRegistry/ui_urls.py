from django.urls import path

from . import views

urlpatterns = [
    path('queue/', views.queue_view, name='docs_queue'),
    path('revision/<int:pk>/', views.revision_view, name='docs_revision'),
    path('entry/<int:code>/', views.entry_view, name='docs_entry'),
    path('remark/<int:pk>/sheet.pdf', views.remark_sheet_pdf, name='docs_remark_sheet'),
    path('issue/<int:pk>/waybill.pdf', views.waybill_pdf, name='docs_waybill'),
    path('issue/<int:pk>/approval.pdf', views.approval_pdf, name='docs_approval'),
]
