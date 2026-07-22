from django.core.management.base import BaseCommand
from TelegramParser.parser import parse_channel


class Command(BaseCommand):
    help = 'Тест: получить данные с Telegram-канала (10 сообщений)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--channel', default='@github_community',
            help='Username канала (по умолчанию @github_community)'
        )
        parser.add_argument(
            '--limit', type=int, default=10,
            help='Количество сообщений (по умолчанию 10)'
        )

    def handle(self, *args, **options):
        channel = options['channel']
        limit = options['limit']

        self.stdout.write(f"ТЕСТ: Парсинг {channel}, limit={limit}")

        found, saved, skipped = parse_channel(
            channel, limit=limit, incremental=False
        )

        self.stdout.write(self.style.SUCCESS(
            f"ТЕСТ ЗАВЕРШЁН! Найдено: {found}, сохранено: {saved}, "
            f"пропущено: {skipped}"
        ))
