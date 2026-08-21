from django.urls import path
from ProjectTDL import views
from ProjectTDL.views import TaskUpdateView, TaskDeleteView, SubTaskDeleteView, SubTaskUpdateView, \
    generate_custom_report

urlpatterns = [
    path("", views.custom_task_view, name='custom_task_view'),
    path("task/<int:pk>/", views.task_detail, name='task_detail'),
    path("TaskUpdateView/<int:pk>", TaskUpdateView.as_view(), name='TaskUpdateView'),
    path("TaskDeleteView/<int:pk>", TaskDeleteView.as_view(), name='TaskDeleteView'),
    path("TaskCloneView/<int:pk>", views.TaskCloneView, name='TaskCloneView'),
    path("SubTaskUpdateView/<int:pk>", SubTaskUpdateView.as_view(), name='SubTaskUpdateView'),
    path("SubTaskDeleteView/<int:pk>", SubTaskDeleteView.as_view(), name='SubTaskDeleteView'),
    path("SubTaskCloneView/<int:pk>", views.SubTaskCloneView, name='SubTaskCloneView'),
    path('manage_ref/', views.manage_reference, name='manage_reference'),
    path('quick_create_task/', views.quick_create_task, name='quick_create_task'),
    path('quick_create_subtask/', views.quick_create_subtask, name='quick_create_subtask'),
    path('cascade_filter_options/', views.cascade_filter_options, name='cascade_filter_options'),
    path('update_task_field/', views.update_task_field, name='update_task_field'),
    path('reports/custom/', generate_custom_report, name='generate_custom_report'),
    path('tree/', views.task_tree_view, name='task_tree_view'),
    path('bulk_update/', views.bulk_update_tasks, name='bulk_update_tasks'),
    path('bulk_delete/', views.bulk_delete_tasks, name='bulk_delete_tasks'),
    path('save_settings/', views.save_user_settings, name='save_user_settings'),
    path('save_filter_state/', views.save_filter_state, name='save_filter_state'),
    path('filter_ajax/', views.filter_tasks_ajax, name='filter_tasks_ajax'),
    path('pinned/list/', views.list_pinned_projects, name='list_pinned_projects'),
    path('pinned/add/', views.add_pinned_project, name='add_pinned_project'),
    path('pinned/remove/', views.remove_pinned_project, name='remove_pinned_project'),
]