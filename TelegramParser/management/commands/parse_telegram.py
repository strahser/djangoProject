from django.core.management.base import BaseCommand

from TelegramParser.parser import parse_channel


class Command(BaseCommand):
    help = 'Парсинг Telegram-канала через API (Telethon)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--channel', required=True,
            help='Username канала (например, @github_community или github_community)'
        )
        parser.add_argument(
            '--api-id', type=int, default=None,
            help='Telegram API ID (если не задан в settings.py)'
        )
        parser.add_argument(
            '--api-hash', default=None,
            help='Telegram API Hash (если не задан в settings.py)'
        )
        parser.add_argument(
            '--limit', type=int, default=None,
            help='Ограничение на количество сообщений'
        )
        parser.add_argument(
            '--full', action='store_true',
            help='Полный парсинг всей истории (по умолчанию инкрементальный)'
        )

    def handle(self, *args, **options):
        channel = options['channel']
        api_id = options['api_id']
        api_hash = options['api_hash']
        limit = options['limit']
        incremental = not options['full']

        mode = 'инкрементальный' if incremental else 'полный'
        self.stdout.write(f"Парсинг канала: {channel} ({mode})")

        found, saved, skipped = parse_channel(
            channel, api_id, api_hash, limit, incremental
        )

        self.stdout.write(self.style.SUCCESS(
            f"Готово! Найдено: {found}, сохранено: {saved}, пропущено (дубли): {skipped}"
        ))
