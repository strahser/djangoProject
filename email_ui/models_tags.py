# -*- coding: utf-8 -*-
"""P2: теги писем email_ui (вынесено из models.py 1:1)."""
from django.conf import settings
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
