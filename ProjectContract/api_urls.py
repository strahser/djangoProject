from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api_views import ContractViewSet, ContractPaymentsViewSet

router = DefaultRouter()
router.register(r'contracts', ContractViewSet, basename='api-contract')
router.register(r'payments', ContractPaymentsViewSet, basename='api-payment')

urlpatterns = [
    path('', include(router.urls)),
]
