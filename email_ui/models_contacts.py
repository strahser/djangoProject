# -*- coding: utf-8 -*-
"""P2: контакты/группы/алиасы email_ui (вынесено из models.py 1:1)."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


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

    def save(self, *args, **kwargs):
        # Унификация ввода: твёрдая почта lower+trim
        from .utils import canonical_email
        canon = canonical_email(self.email or '')
        self.email = canon or (self.email or '').strip()
        super().save(*args, **kwargs)


class ContactGroup(models.Model):
    """Группа адресатов: содержит контакты и/или вложенные группы.

    Выбор группы в пикере раскрывается в плоский список твёрдых почт
    (метод all_emails). Циклы вложенности запрещены (clean + would_cycle).
    """
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    contacts = models.ManyToManyField(
        Contact, blank=True,
        related_name='contact_groups', verbose_name='Контакты',
    )
    subgroups = models.ManyToManyField(
        'self', symmetrical=False, blank=True,
        related_name='parent_groups', verbose_name='Вложенные группы',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Изменена')

    class Meta:
        verbose_name = 'Группа адресатов'
        verbose_name_plural = 'Группы адресатов'
        ordering = ['name']

    def __str__(self):
        return self.name

    def _descendant_ids(self):
        """Id всех вложенных групп (транзитивно), с защитой от циклов в данных."""
        seen, stack = set(), [self.pk]
        out = set()
        while stack:
            gid = stack.pop()
            for sub_id in ContactGroup.objects.filter(
                pk=gid,
            ).values_list('subgroups__pk', flat=True):
                if sub_id is None or sub_id in seen:
                    continue
                seen.add(sub_id)
                out.add(sub_id)
                stack.append(sub_id)
        out.discard(self.pk)
        return out

    def would_cycle(self, subgroup):
        """True, если добавление subgroup создаст цикл (или это она сама)."""
        if subgroup.pk is None or self.pk is None:
            return False
        if subgroup.pk == self.pk:
            return True
        return self.pk in ContactGroup.objects.get(pk=subgroup.pk)._descendant_ids()

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.pk:
            bad = [s for s in self.subgroups.all() if self.would_cycle(s)]
            if bad:
                raise ValidationError({
                    'subgroups': 'Циклическая вложенность запрещена: %s' % (
                        ', '.join(s.name for s in bad)),
                })

    def all_contacts(self):
        """Все контакты группы включая вложенные (плоско, без дублей)."""
        found, stack, seen_groups = {}, [self], {self.pk}
        while stack:
            grp = stack.pop()
            for c in grp.contacts.filter(is_active=True).prefetch_related('emails'):
                found.setdefault(c.pk, c)
            for sub in grp.subgroups.filter(is_active=True):
                if sub.pk not in seen_groups:
                    seen_groups.add(sub.pk)
                    stack.append(sub)
        return list(found.values())

    def all_emails(self):
        """Плоский список твёрдых почт (primary, иначе первая), сортированный."""
        from .utils import canonical_email
        out, seen = [], set()
        for c in self.all_contacts():
            try:
                primary = c.primary_email
                raw = (primary.email if primary else '') or ''
                if not raw:
                    first = c.emails.first()
                    raw = first.email if first else ''
            except Exception:
                raw = ''
            addr = canonical_email(raw or '') or (raw or '').strip()
            if addr and addr.lower() not in seen:
                seen.add(addr.lower())
                out.append(addr)
        return sorted(out, key=str.lower)


class EmailAlias(models.Model):
    """Справочник алиасов: отображаемое имя -> твёрдая почта.

    Только модель-заготовка под будущую работу по алиасам.
    Заполнение и применение — отдельно, после ревью точных совпадений.
    В таблице Email хранится только bare-почта (единое состояние истины).
    """
    SOURCE_CHOICES = [
        ('sender_map', 'Карта отправителей'),
        ('contact', 'Контакт'),
        ('manual', 'Вручную'),
    ]
    alias = models.CharField(
        max_length=200, unique=True, verbose_name='Алиас (имя)',
        help_text='Отображаемое имя как в заголовках писем, lower',
    )
    email = models.EmailField(verbose_name='Твёрдая почта')
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES,
        default='manual', verbose_name='Источник',
    )
    verified = models.BooleanField(
        default=False, verbose_name='Проверен',
        help_text='Применять в миграциях только проверенные',
    )
    note = models.CharField(max_length=300, blank=True, verbose_name='Примечание')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Изменён')

    class Meta:
        verbose_name = 'Алиас почты'
        verbose_name_plural = 'Алиасы почты'
        ordering = ['alias']

    def __str__(self):
        mark = '✓' if self.verified else '?'
        return f'{mark} {self.alias} -> {self.email}'

    def save(self, *args, **kwargs):
        from .utils import canonical_email
        self.alias = (self.alias or '').strip().lower()
        canon = canonical_email(self.email or '')
        self.email = canon or (self.email or '').strip()
        super().save(*args, **kwargs)
