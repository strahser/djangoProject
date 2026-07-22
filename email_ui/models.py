from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class EmailTag(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name='Название')
    color = models.CharField(max_length=7, default='#3498db', verbose_name='Цвет')
    description = models.TextField(blank=True, verbose_name='Описание')
    is_system = models.BooleanField(default=False, verbose_name='Системный')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')

    class Meta:
        verbose_name = 'Тег письма'
        verbose_name_plural = 'Теги писем'
        ordering = ['name']

    def __str__(self):
        return self.name


class EmailEmailTag(models.Model):
    email = models.ForeignKey(
        'Emails.Email', on_delete=models.CASCADE,
        related_name='email_tags', verbose_name='Письмо'
    )
    tag = models.ForeignKey(
        EmailTag, on_delete=models.CASCADE,
        related_name='email_tags', verbose_name='Тег'
    )
    added_at = models.DateTimeField(auto_now_add=True, verbose_name='Добавлен')
    added_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Кто добавил'
    )

    class Meta:
        verbose_name = 'Тег письма (связь)'
        verbose_name_plural = 'Теги писем (связи)'
        unique_together = [['email', 'tag']]

    def __str__(self):
        return f'{self.email} → {self.tag}'


class Contact(models.Model):
    name = models.CharField(max_length=200, verbose_name='Имя')
    company = models.ForeignKey(
        'ProjectContract.Contractor', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Компания'
    )
    position = models.CharField(max_length=100, blank=True, verbose_name='Должность')
    phone = models.CharField(max_length=50, blank=True, verbose_name='Телефон')
    notes = models.TextField(blank=True, verbose_name='Заметки')
    is_active = models.BooleanField(default=True, verbose_name='Активный')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Изменён')

    class Meta:
        verbose_name = 'Контакт'
        verbose_name_plural = 'Контакты'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def primary_email(self):
        return self.emails.filter(is_primary=True).first()


class ContactEmail(models.Model):
    LABEL_CHOICES = [
        ('work', 'Рабочий'),
        ('personal', 'Личный'),
        ('other', 'Другое'),
    ]
    contact = models.ForeignKey(
        Contact, on_delete=models.CASCADE,
        related_name='emails', verbose_name='Контакт'
    )
    email = models.EmailField(verbose_name='Email')
    label = models.CharField(
        max_length=20, choices=LABEL_CHOICES,
        default='work', verbose_name='Тип'
    )
    is_primary = models.BooleanField(default=False, verbose_name='Основной')

    class Meta:
        verbose_name = 'Email контакта'
        verbose_name_plural = 'Email контактов'
        unique_together = [['contact', 'email']]

    def __str__(self):
        return f'{self.email} ({self.contact.name})'


class SMTPAccount(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название')
    host = models.CharField(max_length=200, verbose_name='Хост')
    port = models.IntegerField(default=587, verbose_name='Порт')
    username = models.EmailField(verbose_name='Имя пользователя')
    password = models.CharField(max_length=200, verbose_name='Пароль')
    use_tls = models.BooleanField(default=True, verbose_name='TLS')
    use_ssl = models.BooleanField(default=False, verbose_name='SSL')
    from_email = models.EmailField(verbose_name='Email отправителя')
    from_name = models.CharField(max_length=100, blank=True, verbose_name='Имя отправителя')
    is_default = models.BooleanField(default=False, verbose_name='По умолчанию')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'SMTP аккаунт'
        verbose_name_plural = 'SMTP аккаунты'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_default:
            SMTPAccount.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


class EmailTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    subject_template = models.CharField(max_length=300, verbose_name='Шаблон темы')
    body_template = models.TextField(verbose_name='Шаблон тела письма')
    is_html = models.BooleanField(default=True, verbose_name='HTML')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Создан'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Шаблон письма'
        verbose_name_plural = 'Шаблоны писем'

    def __str__(self):
        return self.name


class EmailTemplateVariable(models.Model):
    template = models.ForeignKey(
        EmailTemplate, on_delete=models.CASCADE,
        related_name='variables', verbose_name='Шаблон'
    )
    name = models.CharField(max_length=50, verbose_name='Переменная')
    label = models.CharField(max_length=100, verbose_name='Описание')
    default_value = models.CharField(max_length=200, blank=True, verbose_name='По умолчанию')
    is_required = models.BooleanField(default=False, verbose_name='Обязательная')

    class Meta:
        verbose_name = 'Переменная шаблона'
        verbose_name_plural = 'Переменные шаблонов'

    def __str__(self):
        return f'{{{{{self.name}}}}}'


class EmailRule(models.Model):
    CONDITION_OPERATORS = [
        ('contains', 'Содержит'),
        ('equals', 'Равно'),
        ('starts_with', 'Начинается с'),
        ('ends_with', 'Заканчивается на'),
        ('regex', 'Регулярное выражение'),
    ]
    ACTION_TYPES = [
        ('add_tag', 'Добавить тег'),
        ('remove_tag', 'Удалить тег'),
        ('move_to_folder', 'Переместить в папку'),
        ('mark_read', 'Отметить прочитанным'),
        ('mark_important', 'Отметить важным'),
        ('forward_to', 'Переслать на email'),
        ('create_task', 'Создать задачу'),
        ('send_auto_reply', 'Отправить автоответ'),
        ('run_webhook', 'Вызвать webhook'),
    ]

    name = models.CharField(max_length=100, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    is_active = models.BooleanField(default=True, verbose_name='Активно')
    priority = models.IntegerField(default=0, verbose_name='Приоритет')

    # JSON conditions
    conditions = models.JSONField(default=dict, verbose_name='Условия', help_text=(
        'Формат: {"field": "subject|sender|receiver|has_attachments", '
        '"operator": "contains|equals|regex", "value": "..."}'
    ))
    # JSON actions
    actions = models.JSONField(default=dict, verbose_name='Действия', help_text=(
        'Формат: {"action": "add_tag", "params": {"tag_id": 1}}'
    ))

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Создал'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Правило автоматизации'
        verbose_name_plural = 'Правила автоматизации'
        ordering = ['-priority']

    def __str__(self):
        return self.name


class EmailAutomationLog(models.Model):
    rule = models.ForeignKey(
        EmailRule, on_delete=models.CASCADE,
        verbose_name='Правило'
    )
    email = models.ForeignKey(
        'Emails.Email', on_delete=models.CASCADE,
        verbose_name='Письмо'
    )
    executed_at = models.DateTimeField(auto_now_add=True, verbose_name='Время выполнения')
    success = models.BooleanField(default=True, verbose_name='Успешно')
    action_taken = models.CharField(
        max_length=200, blank=True, verbose_name='Выполненное действие'
    )
    error_message = models.TextField(blank=True, verbose_name='Ошибка')

    class Meta:
        verbose_name = 'Лог автоматизации'
        verbose_name_plural = 'Логи автоматизации'
        ordering = ['-executed_at']

    def __str__(self):
        return f'{self.rule.name} -> {self.email}'


class SavedFilter(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название')
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Пользователь')
    filters = models.JSONField(verbose_name='Параметры фильтра')
    folder = models.CharField(
        max_length=20, default='inbox', verbose_name='Папка'
    )
    is_default = models.BooleanField(default=False, verbose_name='По умолчанию')
    is_shared = models.BooleanField(default=False, verbose_name='Общий')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Сохранённый фильтр'
        verbose_name_plural = 'Сохранённые фильтры'
        unique_together = [['name', 'user']]

    def __str__(self):
        return self.name


class EmailTaskLink(models.Model):
    LINK_TYPES = [
        ('related', 'Связано'),
        ('created_from', 'Создано из письма'),
        ('created_task', 'Создана задача'),
        ('reference', 'Ссылка'),
    ]
    email = models.ForeignKey(
        'Emails.Email', on_delete=models.CASCADE,
        related_name='task_links', verbose_name='Письмо'
    )
    task = models.ForeignKey(
        'ProjectTDL.Task', on_delete=models.CASCADE,
        related_name='email_links', verbose_name='Задача'
    )
    link_type = models.CharField(
        max_length=20, choices=LINK_TYPES,
        default='related', verbose_name='Тип связи'
    )
    note = models.TextField(blank=True, verbose_name='Примечание')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Кто связал'
    )

    class Meta:
        verbose_name = 'Связь письма с задачей'
        verbose_name_plural = 'Связи писем с задачами'
        unique_together = [['email', 'task']]

    def __str__(self):
        return f'{self.email} ↔ {self.task}'
