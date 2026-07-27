import json
import os
from pathlib import Path

from django.conf import settings
from django.db import models
from django.contrib import admin
from django.contrib.admin import display as admin_display
from django.utils.html import format_html


class Importance(models.IntegerChoices):
    LOW = 1, 'Низкая'
    MEDIUM = 2, 'Средняя'
    HIGH = 3, 'Высокая'
    CRITICAL = 4, 'Критическая'


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    slug = models.SlugField(max_length=100, unique=True, verbose_name='Slug')

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['name']

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Категория'
    )

    class Meta:
        verbose_name = 'Тег'
        verbose_name_plural = 'Теги'
        ordering = ['name']

    def __str__(self):
        return self.name


class TelegramChannel(models.Model):
    name = models.CharField(max_length=200, verbose_name='Название канала')
    username = models.CharField(max_length=200, unique=True, verbose_name='Username (@)')
    channel_id = models.BigIntegerField(null=True, blank=True, verbose_name='Channel ID')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    last_parsed = models.DateTimeField(null=True, blank=True, verbose_name='Последний парсинг')

    creation_stamp = models.DateTimeField(auto_now_add=True, verbose_name='дата создания')
    update_stamp = models.DateTimeField(auto_now=True, verbose_name='дата изменения')

    class Meta:
        verbose_name = 'Канал Telegram'
        verbose_name_plural = 'Каналы Telegram'

    def __str__(self):
        return self.name


class TelegramMessage(models.Model):
    telegram_id = models.BigIntegerField(unique=True, verbose_name='ID сообщения')
    channel = models.ForeignKey(
        TelegramChannel, on_delete=models.CASCADE,
        null=True, blank=True, verbose_name='Канал'
    )
    channel_name = models.CharField(max_length=200, blank=True, verbose_name='Имя канала')
    author = models.CharField(max_length=200, blank=True, verbose_name='Автор')
    text = models.TextField(blank=True, verbose_name='Текст')
    html_text = models.TextField(blank=True, verbose_name='Текст (HTML)')
    date = models.DateTimeField(verbose_name='Дата сообщения')

    tags = models.JSONField(default=list, blank=True, verbose_name='Теги (raw)')
    tag_objects = models.ManyToManyField(Tag, blank=True, verbose_name='Теги')
    links = models.JSONField(default=list, blank=True, verbose_name='Ссылки')
    reactions = models.JSONField(default=dict, blank=True, verbose_name='Реакции')
    total_reactions = models.PositiveIntegerField(default=0, verbose_name='Всего реакций')
    importance = models.IntegerField(
        choices=Importance.choices,
        default=Importance.MEDIUM,
        verbose_name='Важность'
    )

    has_media = models.BooleanField(default=False, verbose_name='Есть медиа')
    media_type = models.CharField(max_length=50, blank=True, verbose_name='Тип медиа')
    is_pinned = models.BooleanField(default=False, verbose_name='Закреплено')
    source = models.CharField(
        max_length=20, default='api',
        choices=[('api', 'API'), ('html', 'HTML-экспорт')],
        verbose_name='Источник'
    )

    content_path = models.CharField(
        max_length=500, blank=True, default='',
        verbose_name='Путь к файлу контента'
    )

    creation_stamp = models.DateTimeField(auto_now_add=True, verbose_name='дата создания')
    update_stamp = models.DateTimeField(auto_now=True, verbose_name='дата изменения')

    class Meta:
        verbose_name = 'Сообщение Telegram'
        verbose_name_plural = 'Сообщения Telegram'
        ordering = ['-date']

    def _get_content_dir(self):
        return getattr(settings, 'TELEGRAM_CONTENT_DIR',
                       os.path.join(settings.BASE_DIR, 'telegram_content'))

    def _content_filepath(self):
        d = os.path.join(self._get_content_dir(), 'telegram_messages')
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f'{self.telegram_id}.json')

    def write_content(self, text='', html_text=''):
        data = {'text': text, 'html_text': html_text}
        fp = self._content_filepath()
        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        self.content_path = os.path.relpath(fp, self._get_content_dir())

    def read_content(self):
        if not self.content_path:
            return None
        fp = os.path.join(self._get_content_dir(), self.content_path)
        if not os.path.exists(fp):
            return None
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def get_text(self):
        if self.text:
            return self.text
        content = self.read_content()
        if content:
            return content.get('text', '')
        return ''

    def get_html(self):
        if self.html_text:
            return self.html_text
        content = self.read_content()
        if content:
            return content.get('html_text', '')
        return ''

    def save(self, *args, **kwargs):
        text_val = self.text or ''
        html_val = self.html_text or ''
        if text_val or html_val:
            self.write_content(text=text_val, html_text=html_val)
            self.text = ''
            self.html_text = ''
        super().save(*args, **kwargs)

    def __str__(self):
        preview = self.get_text()[:80].replace('\n', ' ') if self.get_text() else '(медиа)'
        return f"[{self.channel_name}] {preview}"

    @admin_display(description='Важность', ordering='importance')
    def importance_badge(self):
        colors = {1: 'secondary', 2: 'info', 3: 'warning', 4: 'danger'}
        color = colors.get(self.importance, 'secondary')
        label = self.get_importance_display()
        return format_html('<span class="badge bg-{}">{}</span>', color, label)

    @admin.display(description='Категории')
    def categories_display(self):
        cats = Category.objects.filter(tag__telegrammessage=self).distinct()
        return ', '.join(c.name for c in cats) if cats else '—'


class ParseLog(models.Model):
    channel = models.ForeignKey(
        TelegramChannel, on_delete=models.CASCADE,
        null=True, blank=True, verbose_name='Канал'
    )
    operation = models.CharField(
        max_length=20, default='api',
        choices=[('api', 'API'), ('html', 'HTML-импорт')],
        verbose_name='Операция'
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name='Начало')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='Окончание')
    messages_found = models.PositiveIntegerField(default=0, verbose_name='Найдено')
    messages_saved = models.PositiveIntegerField(default=0, verbose_name='Сохранено')
    messages_skipped = models.PositiveIntegerField(default=0, verbose_name='Пропущено (дубли)')
    status = models.CharField(
        max_length=20, default='running',
        choices=[('running', 'Выполняется'), ('done', 'Завершено'), ('error', 'Ошибка')],
        verbose_name='Статус'
    )
    error_message = models.TextField(blank=True, verbose_name='Ошибка')

    class Meta:
        verbose_name = 'Лог парсинга'
        verbose_name_plural = 'Логи парсинга'
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.get_operation_display()} — {self.channel or 'N/A'} — {self.status}"
