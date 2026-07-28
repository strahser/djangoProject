from django.db import models

from PersonalData.crypto import decrypt_value, encrypt_value


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
    project_site = models.ForeignKey(PersonalProjectSite, verbose_name='Проект', null=False, on_delete=models.CASCADE)
    contractor = models.ForeignKey(PersonalContractor, on_delete=models.CASCADE, verbose_name='Подрядчик')
    name = models.CharField(max_length=200, null=True, verbose_name='Описание')
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="цена")
    proposal_number = models.CharField(max_length=200, null=True, blank=True, verbose_name='Proposal')
    due_date = models.DateField(verbose_name="план.завершение", null=True, blank=True)

    class Meta:
        verbose_name = 'Договор'
        verbose_name_plural = 'Договоры'


class PersonalContractPayments(BaseModel):
    name = models.CharField(max_length=200, null=True, verbose_name='Наименование платежа')
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="цена")
    contract = models.ForeignKey(PersonalContract, on_delete=models.CASCADE, verbose_name='Договор')
    made_payment = models.BooleanField(verbose_name='Оплачено?', default=False)
    due_date = models.DateField(verbose_name="план.завершение", null=True, blank=True)

    class Meta:
        verbose_name = 'договор Оплата'
        verbose_name_plural = 'договоры Оплаты'


class PersonalPassword(BaseModel):
    """Хранилище паролей. Пароль хранится только в зашифрованном виде (Fernet)."""
    CATEGORIES = [
        ('bank', 'Банк'), ('mail', 'Почта'), ('work', 'Работа'),
        ('shop', 'Покупки'), ('social', 'Соцсети'), ('other', 'Прочее'),
    ]
    name = models.CharField(max_length=100, verbose_name='Сервис')
    url = models.CharField(max_length=300, null=True, blank=True, verbose_name='URL')
    login = models.CharField(max_length=200, null=True, blank=True, verbose_name='Логин / e-mail')
    password_enc = models.TextField(verbose_name='Пароль (шифр)')
    category = models.CharField(max_length=20, choices=CATEGORIES, default='other', verbose_name='Категория')
    notes = models.TextField(null=True, blank=True, verbose_name='Заметки')
    favorite = models.BooleanField(default=False, verbose_name='Избранное')

    class Meta:
        verbose_name = 'Пароль'
        verbose_name_plural = 'Пароли'
        ordering = ['-favorite', 'name']

    def set_password(self, raw: str):
        self.password_enc = encrypt_value(raw)

    def get_password(self) -> str:
        return decrypt_value(self.password_enc)

    def save(self, *args, **kwargs):
        # если пароль пришёл в открытом виде через форму-виджет — шифруем
        if self.password_enc and not self._looks_encrypted(self.password_enc):
            self.password_enc = encrypt_value(self.password_enc)
        super().save(*args, **kwargs)

    @staticmethod
    def _looks_encrypted(value: str) -> bool:
        return value.startswith('gAAAAA')


class PersonalNote(BaseModel):
    """Личные заметки / справочная информация."""
    name = models.CharField(max_length=200, verbose_name='Заголовок')
    body = models.TextField(verbose_name='Содержимое')
    tags = models.CharField(max_length=300, null=True, blank=True, verbose_name='Теги (через запятую)')
    pinned = models.BooleanField(default=False, verbose_name='Закреплено')

    class Meta:
        verbose_name = 'Заметка'
        verbose_name_plural = 'Заметки'
        ordering = ['-pinned', '-update_stamp']