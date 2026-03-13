import os
import mimetypes
from django.core.management.base import BaseCommand
from Emails.models import Email, Attachment

class Command(BaseCommand):
    help = 'Создаёт записи Attachment для существующих писем на основе файлов в папке link'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать, что будет сделано, без реальных изменений',
        )
        parser.add_argument(
            '--exclude-patterns',
            nargs='*',
            default=['Image.*.png', 'custom_table_view.html'],
            help='Шаблоны имён файлов для исключения (простая маска с * в начале/конце)'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        exclude_patterns = options['exclude_patterns']

        # Получаем все письма с непустым link и существующей папкой
        emails = Email.objects.exclude(link__isnull=True).exclude(link='')
        total_created = 0
        total_skipped = 0

        for email in emails:
            folder = email.link
            if not os.path.isdir(folder):
                self.stdout.write(f"Папка не существует: {folder}")
                continue

            # Получаем список файлов
            try:
                all_files = os.listdir(folder)
            except OSError as e:
                self.stdout.write(self.style.ERROR(f"Ошибка чтения {folder}: {e}"))
                continue

            # Фильтруем: исключаем служебные файлы по паттернам
            files_to_process = []
            for f in all_files:
                full_path = os.path.join(folder, f)
                if not os.path.isfile(full_path):
                    continue
                # Проверка по паттернам (простая замена * на .*)
                exclude = False
                for pattern in exclude_patterns:
                    if pattern.startswith('*') and pattern.endswith('*'):
                        if pattern[1:-1] in f:
                            exclude = True
                            break
                    elif pattern.startswith('*'):
                        if f.endswith(pattern[1:]):
                            exclude = True
                            break
                    elif pattern.endswith('*'):
                        if f.startswith(pattern[:-1]):
                            exclude = True
                            break
                    elif pattern == f:
                        exclude = True
                        break
                if not exclude:
                    files_to_process.append(f)

            for filename in files_to_process:
                full_path = os.path.join(folder, filename)

                # Проверяем, существует ли уже запись для этого письма с таким именем
                if Attachment.objects.filter(email=email, filename=filename).exists():
                    total_skipped += 1
                    continue

                # Получаем размер и content_type
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    size = 0
                content_type, _ = mimetypes.guess_type(filename)
                if not content_type:
                    content_type = 'application/octet-stream'

                if dry_run:
                    self.stdout.write(f"[DRY RUN] Создам: {email.id} - {filename}")
                else:
                    Attachment.objects.create(
                        email=email,
                        file_path=full_path,
                        filename=filename,
                        size=size,
                        content_type=content_type
                    )
                    total_created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Готово. Создано: {total_created}, пропущено (уже есть): {total_skipped}"
        ))