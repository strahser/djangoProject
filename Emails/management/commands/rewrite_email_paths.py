# -*- coding: utf-8 -*-
"""Переписать сохранённые пути писем/вложений под текущий корень архива.

В БД лежат абсолютные пути, исторически с корнем ``e:\\...``. Диск переехал
(сейчас ``d:\\...``, новые письма пишутся в ``E_MAIL_DIRECTORY``). Команда
заменяет только корень, не трогая хвост
(``imap_attachments\\INBOX\\<папка>\\<файл>``).

По умолчанию — dry-run: показывает, что будет изменено, но ничего не пишет.

    python manage.py rewrite_email_paths
    python manage.py rewrite_email_paths --apply
    python manage.py rewrite_email_paths --old "e:\\..." --new "d:\\..." --apply

Если ``--old`` не указан, команда сначала проверяет смену диска: когда все
пути архива лежат на другом диске, чем ``E_MAIL_DIRECTORY``, заменяется
только буква диска (``e:`` → ``d:``). Иначе определяется единственный
старый корень по каталогам ``imap_attachments`` / ``sent`` / ``drafts``.
"""
from collections import Counter
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from Emails.models import Attachment, Email
from Emails.paths import archive_root, split_archive_tail

#: Модели и поля с абсолютными путями к архиву.
TARGETS = ((Email, 'link'), (Attachment, 'file_path'))


def _normalize(path) -> str:
    return str(path or '').replace('/', '\\').rstrip('\\')


def _rebased(path, old_root: str, new_root: str):
    """Заменить корень, если путь начинается с него (граница каталога)."""
    normalized = str(path).replace('/', '\\')
    prefix = old_root.rstrip('\\') + '\\'
    if not normalized.lower().startswith(prefix.lower()):
        return None
    rest = normalized[len(prefix) - 1:]  # начинается с '\'
    return new_root.rstrip('\\') + rest


class Command(BaseCommand):
    help = ('Заменить старый корень архива в Email.link и Attachment.file_path '
            'на текущий E_MAIL_DIRECTORY. Без --apply — только показать.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--old', default=None,
            help='старый корень (по умолчанию определяется автоматически)')
        parser.add_argument(
            '--new', default=None,
            help='новый корень (по умолчанию E_MAIL_DIRECTORY)')
        parser.add_argument(
            '--apply', action='store_true',
            help='записать изменения (без флага — dry-run)')
        parser.add_argument(
            '--limit', type=int, default=0,
            help='не более N записей на модель (0 — все)')

    def handle(self, *args, **options):
        new_root = _normalize(options['new'] or archive_root())
        if not new_root:
            self.stderr.write(
                'Не задан новый корень: укажите --new или E_MAIL_DIRECTORY.')
            return

        old_root = _normalize(options['old']) if options['old'] else None
        if old_root is None:
            drive = None
            if not options['new']:
                drive = self._detect_legacy_drive(new_root)
            if drive:
                old_root = drive
                new_root = new_root[:2]
                self.stdout.write(
                    f'Обнаружена смена диска: {old_root} → {new_root}')
            else:
                old_root = self._detect_old_root(new_root)
                if old_root is None:
                    self.stdout.write('Старых путей не найдено — менять нечего.')
                    return
                self.stdout.write(
                    f'Старый корень определён автоматически: {old_root}')

        if old_root.lower() == new_root.lower():
            self.stdout.write('Старый и новый корень совпадают — менять нечего.')
            return

        self.stdout.write(f'Старый корень: {old_root}')
        self.stdout.write(f'Новый корень: {new_root}')

        apply = options['apply']
        limit = options['limit']
        changed_total = 0

        with transaction.atomic():
            for model, field in TARGETS:
                label = f'{model.__name__}.{field}'
                qs = (model.objects
                      .exclude(**{f'{field}__isnull': True})
                      .exclude(**{field: ''})
                      .filter(**{f'{field}__istartswith': old_root + '\\'})
                      .order_by('pk'))
                if limit:
                    qs = qs[:limit]

                changed = 0
                samples = []
                for obj in qs.iterator():
                    old_value = getattr(obj, field)
                    new_value = _rebased(old_value, old_root, new_root)
                    if not new_value or new_value == old_value:
                        continue
                    if len(samples) < 3:
                        samples.append((obj.pk, old_value, new_value))
                    if apply:
                        model.objects.filter(pk=obj.pk).update(
                            **{field: new_value})
                    changed += 1

                changed_total += changed
                self.stdout.write(f'{label}: к замене {changed}')
                for pk, old_value, new_value in samples:
                    self.stdout.write(f'  id={pk}: {old_value}')
                    self.stdout.write(f'        -> {new_value}')

        if apply:
            self.stdout.write(self.style.SUCCESS(
                f'Обновлено записей: {changed_total}'))
        else:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN: найдено {changed_total} записей. '
                f'Повторите с --apply, чтобы записать.'))

    def _detect_legacy_drive(self, new_root: str):
        """Определить старый диск, если все пути архива на одном чужом диске."""
        new_drive = os.path.splitdrive(new_root)[0]
        if not new_drive:
            return None
        drives = Counter()
        for model, field in TARGETS:
            values = (model.objects
                      .exclude(**{f'{field}__isnull': True})
                      .exclude(**{field: ''})
                      .values_list(field, flat=True))
            for path in values.iterator():
                normalized = str(path).replace('/', '\\')
                if not split_archive_tail(normalized):
                    continue
                drive = os.path.splitdrive(normalized)[0]
                if not drive or drive.lower() == new_drive.lower():
                    continue
                drives[drive.lower()] += 1
        if len(drives) == 1:
            return next(iter(drives))
        return None

    def _detect_old_root(self, new_root: str):
        """Определить единственный старый корень по хвостам путей."""
        prefixes = Counter()
        for model, field in TARGETS:
            values = (model.objects
                      .exclude(**{f'{field}__isnull': True})
                      .exclude(**{field: ''})
                      .values_list(field, flat=True))
            for path in values.iterator():
                normalized = str(path).replace('/', '\\')
                tail = split_archive_tail(normalized)
                if not tail:
                    continue
                index = normalized.lower().rfind(tail.lower())
                if index <= 0:
                    continue
                prefix = normalized[:index].rstrip('\\')
                if prefix.lower() == new_root.lower():
                    continue
                prefixes[prefix] += 1

        if not prefixes:
            return None
        if len(prefixes) > 1:
            self.stderr.write('Найдено несколько старых корней — укажите --old:')
            for prefix, count in prefixes.most_common(10):
                self.stderr.write(f'  {count:>6}  {prefix}')
            return None
        return prefixes.most_common(1)[0][0]
