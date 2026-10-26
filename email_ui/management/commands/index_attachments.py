# -*- coding: utf-8 -*-
"""Индексация текста вложений для полнотекстового поиска.

По умолчанию — только непроиндексированные (text_indexed=False).
Отсутствующие файлы пропускаются без пометки (диск может быть недоступен).
"""
from django.core.management.base import BaseCommand

from email_ui.services.file_text import index_attachment


class Command(BaseCommand):
    help = 'Извлечь текст вложений в БД для поиска'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='переиндексировать и уже помеченные')
        parser.add_argument(
            '--limit', type=int, default=0,
            help='максимум вложений (0 — без лимита)')

    def handle(self, *args, **options):
        from Emails.models import Attachment
        qs = Attachment.objects.all().order_by('id')
        if not options['force']:
            qs = qs.filter(text_indexed=False)
        if options['limit']:
            qs = qs[:options['limit']]
        total, done, skipped, failed = 0, 0, 0, 0
        for att in qs.iterator():
            total += 1
            try:
                index_attachment(att)
                done += 1
            except FileNotFoundError:
                skipped += 1
            except Exception as e:
                failed += 1
                self.stderr.write(f'  {att.pk} {att.filename}: {e}')
        self.stdout.write(
            f'всего: {total}, проиндексировано: {done}, '
            f'нет файла: {skipped}, ошибок: {failed}')
