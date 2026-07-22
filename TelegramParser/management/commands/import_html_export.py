import os
from django.core.management.base import BaseCommand, CommandError
from loguru import logger

from TelegramParser.html_importer import import_html_file, import_html_directory
from TelegramParser.models import ParseLog


class Command(BaseCommand):
    help = 'Импорт сообщений Telegram из HTML-экспорта'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path', required=True,
            help='Путь к файлу messages.html или папке с экспортом'
        )
        parser.add_argument(
            '--channel-name', default=None,
            help='Имя канала (переопределяет из HTML)'
        )
        parser.add_argument(
            '--channel-username', default=None,
            help='Username канала без @'
        )

    def handle(self, *args, **options):
        path = options['path']
        channel_name = options['channel_name']
        channel_username = options['channel_username']

        if not os.path.exists(path):
            raise CommandError(f"Путь не существует: {path}")

        if os.path.isdir(path):
            self.stdout.write(f"Импорт из директории: {path}")
            found, saved, skipped = import_html_directory(path, channel_name, channel_username)
        else:
            self.stdout.write(f"Импорт из файла: {path}")
            found, saved, skipped = import_html_file(path, channel_name, channel_username)

        self.stdout.write(self.style.SUCCESS(
            f"Готово! Найдено: {found}, сохранено: {saved}, пропущено (дубли): {skipped}"
        ))
