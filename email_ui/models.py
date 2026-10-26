from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()

# Переехавшие модели — ре-экспорт: десятки мест импортируют их из .models
# (admin/forms/views/services/tests/Emails). Состояние миграций не меняется
# (app_label + имя модели те же), makemigrations --check это подтверждает.
from .models_automation import EmailAutomationLog, EmailRule
from .models_contacts import Contact, ContactEmail, ContactGroup, EmailAlias
from .models_tags import EmailEmailTag, EmailTag
from .models_templates import EmailTemplate, EmailTemplateVariable


class EmailViewSettings(models.Model):
    """Персональные настройки отображения списка писем.

    show_body_preview — показывать под темой письма первые символы его
    содержания (поле Email.body_text). Длина превью — preview_length.
    """
    MIN_PREVIEW_LENGTH = 40
    MAX_PREVIEW_LENGTH = 300
    DEFAULT_PREVIEW_LENGTH = 120
    MAX_SIGNATURE_LENGTH = 5000
    # Подпись по умолчанию (была зашита в композер): используется, пока
    # пользователь не задал свою в «Настройках почты».
    DEFAULT_SIGNATURE = (
        '<br><br><div style="font-family: Arial, sans-serif; font-size: 13px; '
        'color: #333; margin-top: 20px; border-top: 1px solid #ccc; '
        'padding-top: 10px;">'
        '<strong>Страхов Сергей | Strakhov Sergey</strong><br>'
        'Строительный департамент | Construction department<br>'
        'ООО "ТиЭйч-РУС Милк Фуд" | TH-RUS Milk Food LLC<br>'
        '127055, г Москва, Лесная, д. 61, Стр 2, Эт Цок Пом I ком 27<br>'
        'Mobile: +7 (966)0351073<br>'
        'Website: <a href="http://www.cimrus.com">http://www.cimrus.com</a>'
        '</div>'
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='email_view_settings', verbose_name='Пользователь',
    )
    show_body_preview = models.BooleanField(
        default=True, verbose_name='Показывать начало текста под темой письма',
    )
    preview_length = models.PositiveIntegerField(
        default=DEFAULT_PREVIEW_LENGTH, verbose_name='Символов в превью',
    )
    signature_html = models.TextField(
        blank=True, default='', verbose_name='Подпись (HTML)',
        help_text='Вставляется кнопкой подписи в композере. Пусто — подпись по умолчанию.',
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'Настройки почты'
        verbose_name_plural = 'Настройки почты'

    def __str__(self):
        return f'Настройки почты {self.user}'

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.preview_length is not None and not (
            self.MIN_PREVIEW_LENGTH <= self.preview_length <= self.MAX_PREVIEW_LENGTH
        ):
            raise ValidationError({
                'preview_length': (
                    f'От {self.MIN_PREVIEW_LENGTH} до {self.MAX_PREVIEW_LENGTH} символов'
                ),
            })

    def clamp_preview_length(self):
        self.preview_length = max(
            self.MIN_PREVIEW_LENGTH,
            min(self.MAX_PREVIEW_LENGTH, int(self.preview_length or self.DEFAULT_PREVIEW_LENGTH)),
        )


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
        # Унификация ввода: почты lower+trim
        from .utils import canonical_email
        for field in ('username', 'from_email'):
            val = getattr(self, field, '') or ''
            canon = canonical_email(val)
            setattr(self, field, canon or val.strip())
        super().save(*args, **kwargs)


class SavedFilter(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название')
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Пользователь')
    filters = models.JSONField(verbose_name='Параметры фильтра')
    folder = models.CharField(
        max_length=20, default='inbox', verbose_name='Папка'
    )
    is_pinned = models.BooleanField(
        default=False, verbose_name='Закреплён в сайдбаре')
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
    task_node = models.ForeignKey(
        'ProjectTDL.TaskNode', on_delete=models.CASCADE,
        related_name='email_links', verbose_name='Задача',
        null=True, blank=True
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
        unique_together = [['email', 'task_node']]

    def __str__(self):
        return f'{self.email} ↔ {self.task_node}'
