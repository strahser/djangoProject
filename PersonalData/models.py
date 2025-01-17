from django.db import models


class BaseModel(models.Model):
    name = models.CharField(max_length=100, null=False)
    creation_stamp = models.DateTimeField(auto_now_add=True, null=True, verbose_name="дата создания")
    update_stamp = models.DateTimeField(auto_now=True, null=True, verbose_name="дата изменения")

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class PersonalProjectSite(BaseModel):
    name = models.CharField(max_length=100, null=False, verbose_name='Наименование Проекта')

    class Meta:
        verbose_name = 'Проект'
        verbose_name_plural = 'Проекты'


class PersonalContractor(BaseModel):
    name = models.CharField(max_length=200, null=True, verbose_name='Наименование')

    class Meta:
        verbose_name = 'Ресурс'
        verbose_name_plural = 'Ресурс'


class PersonalContract(BaseModel):
    project_site = models.ForeignKey(PersonalProjectSite, verbose_name='Проект',
                                     null=False,
                                     on_delete=models.CASCADE
                                     )
    contractor = models.ForeignKey(PersonalContractor, on_delete=models.CASCADE, verbose_name='Подрядчик')
    name = models.CharField(max_length=200, null=True, verbose_name='Описание')
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="цена")
    proposal_number = models.CharField(max_length=200, null=True, blank=True, verbose_name='Proposal')
    due_date = models.DateField(verbose_name="план.завершение", null=True, blank=True, )

    class Meta:
        verbose_name = 'Договор'
        verbose_name_plural = 'Договоры'


class PersonalContractPayments(BaseModel):
    name = models.CharField(max_length=200, null=True, verbose_name='Наименование платежа')
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="цена")
    contract = models.ForeignKey(PersonalContract, on_delete=models.CASCADE, verbose_name='Договор')
    made_payment = models.BooleanField(verbose_name='Оплачено?', default=False)
    due_date = models.DateField(verbose_name="план.завершение", null=True, blank=True, )

    class Meta:
        verbose_name = 'договор Оплата'
        verbose_name_plural = 'договоры Оплаты'
