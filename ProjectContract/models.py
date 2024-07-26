from django.db import models
from mptt.models import MPTTModel, TreeForeignKey

class BaseModel(models.Model):
	creation_stamp = models.DateTimeField(auto_now_add=True, null=True, verbose_name="дата создания")
	update_stamp = models.DateTimeField(auto_now=True, null=True, verbose_name="дата изменения")

	class Meta:
		abstract = True


class Contractor(BaseModel):
	name = models.CharField(max_length=200, null=True, verbose_name='Наименование')

	class Meta:
		verbose_name = 'Подрядчик'
		verbose_name_plural = 'Подрядчики'

	def __str__(self):
		return self.name


class Contract(BaseModel):
	project_site = models.ForeignKey('StaticData.ProjectSite', verbose_name='Проект',
	                                 null=False,
	                                 on_delete=models.CASCADE
	                                 )
	contractor = models.ForeignKey('ProjectContract.Contractor', on_delete=models.CASCADE, verbose_name='Подрядчик')
	name = models.CharField(max_length=200, null=True, verbose_name='Описание')
	price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="цена")
	proposal_number = models.CharField(max_length=200, null=True, blank=True, verbose_name='Proposal')
	start_date = models.DateField(verbose_name="план.начало", null=True, blank=True, )
	due_date = models.DateField(verbose_name="план.завершение", null=True, blank=True, )
	duration = models.FloatField(verbose_name="длительность", null=True, blank=True, )

	class Meta:
		verbose_name = 'Договор'
		verbose_name_plural = 'Договоры'

	def __str__(self):
		return self.name


class ContractPayments(MPTTModel):
	name = models.CharField(max_length=200, null=True, verbose_name='Наименование платежа')
	price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="цена")
	contract = models.ForeignKey('ProjectContract.Contract', on_delete=models.CASCADE, verbose_name='Договор')
	parent = TreeForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
	made_payment = models.BooleanField(verbose_name='Оплачено?', default=False)
	start_date = models.DateField(verbose_name="план.начало", null=True, blank=True, )
	duration = models.FloatField(verbose_name="длительность", null=True, blank=True, )
	due_date = models.DateField(verbose_name="план.завершение", null=True, blank=True, )
	creation_stamp = models.DateTimeField(auto_now_add=True, null=True, verbose_name="дата создания")
	update_stamp = models.DateTimeField(auto_now=True, null=True, verbose_name="дата изменения")

	class MPTTMeta:
		order_insertion_by = ['start_date']
	class Meta:
		verbose_name = 'договор Оплата'
		verbose_name_plural = 'договоры Оплаты'

	def __str__(self):
		return f'{self.contract.name}-{self.name}'
