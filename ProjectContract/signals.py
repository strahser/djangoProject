"""Сигналы ProjectContract (Ф2): пересчёт ДДС при изменении платежей."""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from ProjectContract.models import ContractPayments
from ProjectContract.services import rebuild_cashflow


@receiver(post_save, sender=ContractPayments)
def payment_saved(sender, instance, **kwargs):
    rebuild_cashflow(instance.contract)


@receiver(post_delete, sender=ContractPayments)
def payment_deleted(sender, instance, **kwargs):
    rebuild_cashflow(instance.contract)
