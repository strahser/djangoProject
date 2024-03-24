from django.db import models


class Contractor(models.Model):
    name = models.CharField(max_length=200, null=True, verbose_name='Наименование')

    class Meta:
        verbose_name = 'Подрядчик'
        verbose_name_plural = 'Подрядчики'

    def __str__(self):
        return self.name


class Contract(models.Model):
    name = models.CharField(max_length=200, null=True, verbose_name='Описание')
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="цена")
    contractor = models.ForeignKey('ProjectContract.Contractor', on_delete=models.CASCADE, verbose_name='Подрядчик')

    class Meta:
        verbose_name = 'Договор'
        verbose_name_plural = 'Договоры'

    def __str__(self):
        return self.name


class ContractPayments(models.Model):
    name = models.CharField(max_length=200, null=True, verbose_name='Наименование платежа')
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="цена")
    contract = models.ForeignKey('ProjectContract.Contract', on_delete=models.CASCADE, verbose_name='Договор')
    made_payment = models.BooleanField(verbose_name='Оплачено?', default=False)

    class Meta:
        verbose_name = 'договор Оплата'
        verbose_name_plural = 'договоры Оплаты'

    def __str__(self):
        return f'{self.contract.name}-{self.name}'
