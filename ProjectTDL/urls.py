from django.urls import path, include, re_path

from ProjectTDL import views

urlpatterns = [
    path("", views.index, name='home'),
    path("e_mail_add/", views.e_mail_add, name='e_mail_add'),

]
