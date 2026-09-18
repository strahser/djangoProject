import json

from django.utils.dateparse import parse_date
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response

from .models import Contract, ContractPayments
from .serializers import ContractSerializer, ContractPaymentsSerializer
from .services import log_change


def _diff_details(old_data: dict, new_data: dict) -> str:
    """Return human-readable diff of changed fields."""
    changes = []
    for k, v in new_data.items():
        if k in ('id', 'creation_stamp', 'update_stamp'):
            continue
        old = old_data.get(k)
        if old != v:
            changes.append(f'{k}: {old} -> {v}')
    return '; '.join(changes) if changes else 'no field changes'


class ContractViewSet(viewsets.ModelViewSet):
    """
    CRUD по договорам (/api/v1/contracts/).
    Token-авторизация для записи; чтение доступно сессионным юзером.
    """
    queryset = Contract.objects.all().order_by('id')
    serializer_class = ContractSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        obj = serializer.save()
        log_change(
            contract=obj, action='api:create',
            details=f'{obj.name} (id={obj.pk}, price={obj.price})',
            user=self.request.user if self.request.user.is_authenticated else None,
        )

    def perform_update(self, serializer):
        old_data = ContractSerializer(serializer.instance).data
        obj = serializer.save()
        details = _diff_details(old_data, ContractSerializer(obj).data)
        log_change(
            contract=obj, action='api:update',
            details=details,
            user=self.request.user if self.request.user.is_authenticated else None,
        )

    def perform_destroy(self, instance):
        details = f'{instance.name} (id={instance.pk}, price={instance.price})'
        log_change(
            contract=instance, action='api:delete',
            details=details,
            user=self.request.user if self.request.user.is_authenticated else None,
        )
        instance.delete()


class ContractPaymentsViewSet(viewsets.ModelViewSet):
    """
    CRUD по платежам (/api/v1/payments/).
    Фильтр по ?contract=<id> —便捷 для API-агента.
    Token-авторизация для записи.
    """
    queryset = ContractPayments.objects.all().order_by('id')
    serializer_class = ContractPaymentsSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        contract_id = self.request.query_params.get('contract')
        if contract_id is not None:
            qs = qs.filter(contract_id=contract_id)
        return qs

    def perform_create(self, serializer):
        obj = serializer.save()
        log_change(
            contract=obj.contract, payment=obj,
            action='api:create',
            details=f'{obj.name} (id={obj.pk}, price={obj.price}, status={obj.status})',
            user=self.request.user if self.request.user.is_authenticated else None,
        )

    def perform_update(self, serializer):
        old_data = ContractPaymentsSerializer(serializer.instance).data
        obj = serializer.save()
        details = _diff_details(old_data, ContractPaymentsSerializer(obj).data)
        log_change(
            contract=obj.contract, payment=obj,
            action='api:update',
            details=details,
            user=self.request.user if self.request.user.is_authenticated else None,
        )

    def perform_destroy(self, instance):
        details = f'{instance.name} (id={instance.pk}, price={instance.price})'
        log_change(
            contract=instance.contract, payment=instance,
            action='api:delete',
            details=details,
            user=self.request.user if self.request.user.is_authenticated else None,
        )
        instance.delete()
