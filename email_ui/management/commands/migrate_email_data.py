import re
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from Emails.models import Attachment, Email
from email_ui.models import Contact, ContactEmail, EmailRule, SavedFilter, SMTPAccount

User = get_user_model()


class Command(BaseCommand):
    help = 'Миграция данных из Emails в email_ui: контакты, SMTP, правила, фильтры'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Показать что будет сделано без сохранения')
        parser.add_argument('--skip-contacts', action='store_true', help='Пропустить извлечение контактов')
        parser.add_argument('--skip-smtp', action='store_true', help='Пропустить создание SMTP аккаунта')
        parser.add_argument('--skip-rules', action='store_true', help='Пропустить миграцию правил и фильтров')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if not options['skip_contacts']:
            self._migrate_contacts(dry_run)

        if not options['skip_smtp']:
            self._create_default_smtp(dry_run)

        if not options['skip_rules']:
            self._migrate_rules(dry_run)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN: изменения не сохранены'))

    def _extract_email_addresses(self, raw):
        if not raw:
            return []
        emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', raw)
        return [e.lower() for e in emails]

    @transaction.atomic
    def _migrate_contacts(self, dry_run):
        self.stdout.write('Извлечение контактов из существующих писем...')
        sender_map = defaultdict(list)
        for email in Email.objects.exclude(sender__isnull=True).exclude(sender=''):
            for addr in self._extract_email_addresses(email.sender):
                sender_map[addr].append(email.sender)
        for email in Email.objects.exclude(receiver__isnull=True).exclude(receiver=''):
            for addr in self._extract_email_addresses(email.receiver):
                sender_map[addr].append(email.receiver)

        created = 0
        skipped = 0
        for addr, raw_senders in sorted(sender_map.items()):
            if ContactEmail.objects.filter(email=addr).exists():
                skipped += 1
                continue
            # Ищем лучший raw-источник для извлечения имени
            best_raw = self._find_best_raw_for_name(addr, raw_senders)
            name = self._extract_name(best_raw, addr)
            contact = Contact.objects.create(name=name or addr.split('@')[0])
            ContactEmail.objects.create(contact=contact, email=addr, is_primary=True)
            created += 1

        msg = f'Контакты: создано {created}, пропущено (уже есть) {skipped}'
        if dry_run:
            self.stdout.write(f'[DRY-RUN] Будет создано: {len(sender_map)} контактов')
        else:
            self.stdout.write(self.style.SUCCESS(msg))

    @staticmethod
    def _find_best_raw_for_name(addr, raw_list):
        """Находит лучшую строку для извлечения имени контакта."""
        addr_lower = addr.lower().rstrip('.')
        # Лучший кандидат — самая короткая строка содержащая email (короткие = чистые имена)
        candidates = [r for r in raw_list if addr_lower in r.lower()]
        if not candidates:
            return raw_list[0] if raw_list else addr
        # Из кандидатов выбираем самую короткую
        return min(candidates, key=len)

    @staticmethod
    def _extract_name(raw, email_addr):
        """Извлекает имя контакта из строки отправителя."""
        if not raw:
            return email_addr.split('@')[0]

        # Формат "Name <email@domain>" или "['Name'] <email@domain>"
        if '<' in raw:
            before_bracket = raw.split('<')[0].strip()
            # Убираем скобки/кавычки/запятые из списка имён: "['Name1', 'Name2']" -> ищем имя для email
            before_bracket = before_bracket.strip("[]'\" ")
            if ',' in before_bracket:
                # Список имён — для данного email имя не найдено
                before_bracket = ''
            if before_bracket and '@' not in before_bracket:
                return before_bracket

        # Простая строка без @ — это имя
        clean = raw.strip().strip("[]'\"")
        if '@' not in clean:
            return clean

        return email_addr.split('@')[0]

    @transaction.atomic
    def _create_default_smtp(self, dry_run):
        self.stdout.write('Создание SMTP аккаунта по умолчанию...')
        try:
            from django.conf import settings
            host = settings.YA_HOST
            user = settings.YA_USER
            password = settings.YA_PASSWORD
        except (ImportError, AttributeError):
            try:
                from Emails.ЕmailParser.EmailConfig import YA_HOST, YA_USER, YA_PASSWORD
                host, user, password = YA_HOST, YA_USER, YA_PASSWORD
            except ImportError:
                self.stdout.write(self.style.WARNING('Не удалось получить SMTP данные'))
                return

        if not user or not password:
            self.stdout.write(self.style.WARNING('SMTP credentials не настроены'))
            return

        exists = SMTPAccount.objects.filter(username=user).exists()
        if exists:
            self.stdout.write('SMTP аккаунт уже существует')
            return

        if not dry_run:
            SMTPAccount.objects.create(
                name='Yandex SMTP',
                host='smtp.yandex.ru',
                port=465,
                username=user,
                password=password,
                from_email=user,
                from_name=user.split('@')[0],
                is_default=True,
                use_ssl=True,
                use_tls=False,
            )
            self.stdout.write(self.style.SUCCESS('SMTP аккаунт создан'))
        else:
            self.stdout.write('[DRY-RUN] Будет создан SMTP аккаунт')

    @transaction.atomic
    def _migrate_rules(self, dry_run):
        self.stdout.write('Миграция правил и фильтров...')
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            admin = User.objects.first()
        if not admin:
            self.stdout.write(self.style.WARNING('Нет пользователей для назначения правил'))
            return

        if not EmailRule.objects.exists() and not dry_run:
            EmailRule.objects.create(
                name='Авто-важные',
                description='Помечает письма с пометкой "важно"',
                is_active=True,
                priority=50,
                conditions=[{'field': 'subject', 'operator': 'contains', 'value': 'важно'}],
                actions=[{'action': 'mark_important', 'params': {}}],
                created_by=admin,
            )
            self.stdout.write(self.style.SUCCESS('Создано правило "Авто-важные"'))
        elif not dry_run:
            self.stdout.write('Правила уже существуют')

        if not SavedFilter.objects.exists() and not dry_run:
            SavedFilter.objects.create(
                name='Непрочитанные',
                user=admin,
                filters={'is_unread': ['1']},
                folder='inbox',
                is_default=True,
            )
            self.stdout.write(self.style.SUCCESS('Создан фильтр "Непрочитанные"'))
