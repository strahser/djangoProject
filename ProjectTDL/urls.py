from django.urls import path, include, re_path

from ProjectTDL import views
from ProjectTDL.views import TaskUpdateView, TaskDeleteView, SubTaskDeleteView, SubTaskUpdateView, SelectEmailView, \
    EditEmailFormView

urlpatterns = [
    path("", views.custom_task_view, name='custom_task_view'),
    path("TaskUpdateView/<int:pk>", TaskUpdateView.as_view(), name='TaskUpdateView'),
    path("TaskDeleteView/<int:pk>", TaskDeleteView.as_view(), name='TaskDeleteView'),
    path("TaskCloneView/<int:pk>", views.TaskCloneView, name='TaskCloneView'),
    path('handle_incoming_email/', views.handle_incoming_email, name='handle_incoming_email'),
    path("SubTaskUpdateView/<int:pk>", SubTaskUpdateView.as_view(), name='SubTaskUpdateView'),
    path("SubTaskDeleteView/<int:pk>", SubTaskDeleteView.as_view(), name='SubTaskDeleteView'),
    path("SubTaskCloneView/<int:pk>", views.SubTaskCloneView, name='SubTaskCloneView'),
    path("e_mail_add/", views.e_mail_add, name='e_mail_add'),
    path('select-email/<int:task_id>/', SelectEmailView.as_view(), name='select_email'),
    path('update_task_field/', views.update_task_field, name='update_task_field'),

     path('edit-email-form/', EditEmailFormView.as_view(), name='edit_email_form'),


]
