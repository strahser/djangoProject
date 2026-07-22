from django.urls import path
from . import views

app_name = 'TelegramParser'

urlpatterns = [
    path('fetch/<int:channel_id>/', views.fetch_channel_data, name='fetch_channel_data'),
    path('status/', views.parse_status, name='parse_status'),
]
