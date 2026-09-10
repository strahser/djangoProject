"""Токен API для ИИ-агента конвейера РД (M1 DOC-3).

Создаёт (или находит) пользователя docagent и печатает его token:
    python manage.py docs_agent_token
Агент ходит в /api/docs/ с заголовком  Authorization: Token <token>.
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = 'Выдать token API агенту конвейера РД'

    def add_arguments(self, parser):
        parser.add_argument('--user', default='docagent')

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username=options['user'],
            defaults={'is_active': True},
        )
        if created:
            user.set_unusable_password()
            user.save()
        token, _ = Token.objects.get_or_create(user=user)
        self.stdout.write(f'user={user.username} token={token.key}')
