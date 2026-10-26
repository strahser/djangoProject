# -*- coding: utf-8 -*-
"""P2: правила автоматизации email_ui (вынесено из models.py 1:1)."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


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
