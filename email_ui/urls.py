from django.urls import path
from email_ui import views

app_name = 'email_ui'

urlpatterns = [
    path('', views.inbox_view, {'folder': 'inbox'}, name='inbox_default'),
    path('folder/<str:folder>/', views.inbox_view, name='inbox'),
    path('partial/', views.email_list_partial, name='email_list_partial'),
    path('email/<int:pk>/modal/', views.email_detail_modal, name='email_detail_modal'),
    path('email/<int:pk>/body/', views.email_body, name='email_body'),
    path('email/<int:pk>/edit-metadata/', views.edit_metadata, name='edit_metadata'),
    path('email/<int:pk>/edit-metadata-form/', views.edit_metadata_form, name='edit_metadata_form'),
    path('email/<int:pk>/metadata-display/', views.metadata_display, name='metadata_display'),
    path('email/<int:pk>/move-to-folder/', views.move_to_folder, name='move_to_folder'),
    path('email/<int:pk>/attach-to-tasks-modal/', views.attach_to_tasks_modal, name='attach_to_tasks_modal'),
    path('email/<int:pk>/attach-tasks/', views.attach_tasks, name='attach_tasks'),
    path('email/<int:pk>/detach-task/<int:task_id>/', views.detach_task, name='detach_task'),
    path('bulk-action/', views.bulk_action, name='bulk_action'),
    path('unread-count/', views.unread_count, name='unread_count'),
    path('attachment/<int:att_id>/download/', views.download_attachment, name='download_attachment'),
    path('filter-form/partial/', views.filter_form_partial, name='filter_form_partial'),
    path('filter-field-modal/<str:field_name>/', views.filter_field_modal, name='filter_field_modal'),
    # Новый маршрут для получения почты
    path('fetch-emails/', views.fetch_emails, name='fetch_emails'),
    path('email/<int:pk>/mark-read/', views.mark_email_as_read, name='mark_email_as_read'),
]