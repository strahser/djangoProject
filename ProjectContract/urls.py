from django.urls import path, include, re_path
from ProjectContract import views
urlpatterns = [
    path("payments_gantt/", views.payments_gantt, name='payments_gantt'),

]

