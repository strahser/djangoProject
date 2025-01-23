from django.urls import path

from Emails.views import EditEmailFormView, SelectEmailView
from Emails import views


urlpatterns = [
    path("e_mail_add/", views.e_mail_add, name='e_mail_add'),
    path('handle_incoming_email/', views.handle_incoming_email, name='handle_incoming_email'),
    path('select-email/<int:task_id>/', SelectEmailView.as_view(), name='select_email'),
    path('edit-email-form/', EditEmailFormView.as_view(), name='edit_email_form'),

]