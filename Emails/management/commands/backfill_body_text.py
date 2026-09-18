# -*- coding: utf-8 -*-
"""Заполняет body_text у писем из HTML-файлов на диске.

Использование:
    manage.py backfill_body_text [--batch] [--dry-run] [--refresh-all]

Без флагов — только письма с пустым body_text. С --refresh-all — пересчёт
у всех писем с файлами (чистит застарелые технические прелюдии
«Отправитель:… Вложения:» и дубли темы): обновляются только строки, где
новый текст непуст и отличается; письма без файлов не трогаются.
"""
from django.core.management.base import BaseCommand

from Emails.models import Email


class Command(BaseCommand):
    help = 'Заполняет body_text писем из их HTML-файлов на диске.'

    def add_arguments(self, parser):
        parser.add_argument('--batch', type=int, default=500,
                            help='Размер пачки обновлений через update_fields')
        parser.add_argument('--dry-run', action='store_true',
                            help='Только посчитать, не сохранять')
        parser.add_argument('--refresh-all', action='store_true',
                            help='Пересчитать body_text у всех писем с файлами')

    def handle(self, *args, **options):
        batch_size = options['batch']
        dry_run = options['dry_run']
        refresh_all = options['refresh_all']

        if refresh_all:
            qs = Email.objects.exclude(link__isnull=True).exclude(link='').order_by('pk')
            total = qs.count()
            self.stdout.write(f'Писем с файлами (режим refresh-all): {total}')
        else:
            qs = Email.objects.filter(
                body_text='',
            ).exclude(link__isnull=True).exclude(link='').order_by('pk')
            total = qs.count()
            self.stdout.write(f'Писем c пустым body_text: {total}')
        if dry_run:
            return

        filled = skipped = errors = unchanged = 0
        batch = []
        for email in qs.iterator(chunk_size=batch_size):
            try:
                text = email.extract_body_text()
            except Exception as e:
                errors += 1
                self.stdout.write(f'  err pk={email.pk}: {e}')
                continue
            if not text:
                skipped += 1
                continue
            if refresh_all and text == (email.body_text or ''):
                unchanged += 1
                continue
            email.body_text = text
            batch.append(email)
            filled += 1
            if len(batch) >= batch_size:
                self._save(batch)
                batch = []
                self.stdout.write(
                    f'  заполнено {filled}, без изменений {unchanged}, '
                    f'пропущено {skipped}, ошибок {errors}')

        if batch:
            self._save(batch)

        self.stdout.write(self.style.SUCCESS(
            f'Готово: заполнено {filled}, без изменений {unchanged}, '
            f'пропущено (нет файла) {skipped}, ошибок {errors}'
        ))

    @staticmethod
    def _save(batch):
        Email.objects.bulk_update(batch, ['body_text'])