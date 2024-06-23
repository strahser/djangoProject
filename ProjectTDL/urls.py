from django.urls import path, include, re_path

from ProjectTDL import views
from ProjectTDL.views import TaskUpdateView, TaskDeleteView, SubTaskDeleteView, SubTaskUpdateView

urlpatterns = [
    path("", views.index, name='home'),
    path("TaskUpdateView/<int:pk>", TaskUpdateView.as_view(), name='TaskUpdateView'),
    path("TaskDeleteView/<int:pk>", TaskDeleteView.as_view(), name='TaskDeleteView'),
    path("TaskCloneView/<int:pk>", views.TaskCloneView, name='TaskCloneView'),
    path("task_action", views.task_action, name='task_action'),
    path('handle_incoming_email/',views.handle_incoming_email,name='handle_incoming_email'),


    path("SubTaskUpdateView/<int:pk>", SubTaskUpdateView.as_view(), name='SubTaskUpdateView'),
    path("SubTaskDeleteView/<int:pk>", SubTaskDeleteView.as_view(), name='SubTaskDeleteView'),
    path("SubTaskCloneView/<int:pk>", views.SubTaskCloneView, name='SubTaskCloneView'),
    path("e_mail_add/", views.e_mail_add, name='e_mail_add'),

]
