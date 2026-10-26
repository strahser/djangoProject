# -*- coding: utf-8 -*-
"""Проставление флага has_disk_links по наличию narod_attachment_links.html.

По умолчанию dry-run (только считает), запись — с --apply.
Флаг дальше самоподдерживается: email_body правит его при расхождении.
"""
import os

from django.core.management.base import BaseCommand

from email_ui.utils import DISK_LINKS_FILENAME


class Command(BaseCommand):
    help = 'Посчитать/проставить has_disk_links у писем (по умолчанию dry-run)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='записать флаги в БД (без флага — только подсчёт)')

    def handle(self, *args, **options):
        from Emails.models import Email
        apply = options['apply']
        qs = Email.objects.exclude(link__isnull=True).exclude(link='')
        total, with_file, updated = 0, 0, 0
        ids_to_set = []
        for pk, link in qs.values_list('pk', 'link'):
            total += 1
            try:
                has = os.path.isfile(os.path.join(link, DISK_LINKS_FILENAME))
            except (OSError, ValueError, TypeError):
                has = False
            if has:
                with_file += 1
                ids_to_set.append(pk)
        if apply:
            updated += Email.objects.filter(
                pk__in=ids_to_set, has_disk_links=False).update(has_disk_links=True)
            updated += Email.objects.exclude(
                pk__in=ids_to_set).filter(has_disk_links=True).update(has_disk_links=False)
        self.stdout.write(
            f'каталогов: {total}, с файлом ссылок: {with_file}'
            + (f', обновлено: {updated}' if apply else ' (dry-run, запись — с --apply)'))
