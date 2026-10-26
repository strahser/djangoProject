# -*- coding: utf-8 -*-
"""P2: шаблоны писем email_ui (вынесено из models.py 1:1)."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


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
