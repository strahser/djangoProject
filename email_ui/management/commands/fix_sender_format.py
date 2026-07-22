import re
from django.core.management.base import BaseCommand
from Emails.models import Email


class Command(BaseCommand):
    help = 'Исправляет формат sender/receiver в Emails: извлекает email из "Name <email>" формата'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        fixed_sender = 0
        fixed_receiver = 0

        email_re = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')

        for email in Email.objects.all():
            new_sender = self._clean_field(email.sender, email_re)
            new_receiver = self._clean_field(email.receiver, email_re)

            if new_sender != email.sender:
                fixed_sender += 1
                if not dry_run:
                    email.sender = new_sender

            if new_receiver != email.receiver:
                fixed_receiver += 1
                if not dry_run:
                    email.receiver = new_receiver

            if not dry_run:
                email.save(update_fields=['sender', 'receiver'])

        self.stdout.write(self.style.SUCCESS(
            f'Исправлено: sender={fixed_sender}, receiver={fixed_receiver}'
        ))

    def _clean_field(self, value, email_re):
        if not value:
            return value
        # Если поле содержит < - значит формат "Name <email>"
        if '<' in value:
            # Извлекаем email из скобок
            match = re.search(r'<([^>]+)>', value)
            if match:
                email_addr = match.group(1).strip()
                if email_re.match(email_addr):
                    # Извлекаем имя из части перед <
                    name = value.split('<')[0].strip().strip('" \'')
                    return f'{name} <{email_addr}>' if name else email_addr
            # Если не удалось извлечь email, пробуем найти email в строке
            emails_found = email_re.findall(value)
            if emails_found:
                name = value.split('<')[0].strip().strip('" \'')
                return f'{name} <{emails_found[0]}>' if name else emails_found[0]
            # Если нет email вообще, оставляем как есть (или чистим)
            return value.strip()

        # Если формат без <, проверяем есть ли email
        emails_found = email_re.findall(value)
        if emails_found:
            # Есть email - значит это чистый email адрес
            if len(emails_found) == 1 and emails_found[0] == value.strip():
                return value.strip()
            # Есть email и текст - возможно "Name email@domain"
            name_part = value.replace(emails_found[0], '').strip().strip('" \'')
            return f'{name_part} <{emails_found[0]}>' if name_part else emails_found[0]

        # Нет email - возможно просто имя, оставляем как есть
        return value.strip()
