import re
from django.core.management.base import BaseCommand
from Emails.models import Email
from email_ui.models import Contact, ContactEmail


class Command(BaseCommand):
    help = 'Исправляет sender/sender_name/contact в старых письмах через базу контактов'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limit', type=int, default=0)

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        qs = Email.objects.all().order_by('pk')
        if limit:
            qs = qs[:limit]

        total = qs.count()
        fixed_sender = 0
        fixed_name = 0
        fixed_contact = 0
        skipped = 0

        self.stdout.write(f'Processing {total} emails...')

        for em in qs.iterator():
            raw = em.sender
            if not raw:
                skipped += 1
                continue

            header_name, header_email = self._parse_sender(raw)
            if not header_email:
                skipped += 1
                continue

            contact, corrected = self._lookup_contact(header_name, header_email)

            updates = []
            if corrected != em.sender:
                updates.append('sender')
            if header_name and header_name != em.sender_name:
                updates.append('sender_name')
            if contact and em.contact != contact:
                updates.append('contact')

            if not updates:
                continue

            if not dry_run:
                em.sender = corrected
                if header_name:
                    em.sender_name = header_name
                if contact:
                    em.contact = contact
                em.save(update_fields=updates)

            if 'sender' in updates:
                fixed_sender += 1
            if 'sender_name' in updates:
                fixed_name += 1
            if 'contact' in updates:
                fixed_contact += 1

            self.stdout.write(f'  [{em.pk}] {header_name or "?"} <{header_email}> -> <{corrected}>')

        self.stdout.write(self.style.SUCCESS(
            f'{"[DRY RUN] " if dry_run else ""}'
            f'Done: sender={fixed_sender}, sender_name={fixed_name}, '
            f'contact={fixed_contact}, skipped={skipped}, total={total}'
        ))

    def _parse_sender(self, raw: str):
        match = re.match(r'"?([^"<]*)"?\s*<([^>]+)>', raw.strip())
        if match:
            return match.group(1).strip(), match.group(2).strip()
        if '@' in raw:
            return '', raw.strip()
        return raw.strip(), None

    def _lookup_contact(self, header_name: str, header_email: str):
        best_match = None

        ce = ContactEmail.objects.filter(email__iexact=header_email).first()
        if ce:
            contact = ce.contact
            contact_name = (contact.name or '').lower().strip()
            header_name_lower = header_name.lower().strip() if header_name else ''

            name_match = False
            if not header_name_lower or not contact_name:
                name_match = True
            elif contact_name in header_name_lower or header_name_lower in contact_name:
                name_match = True
            else:
                header_words = set(w for w in header_name_lower.replace('.', ' ').split() if len(w) > 1)
                contact_words = set(w for w in contact_name.replace('.', ' ').split() if len(w) > 1)
                if header_words & contact_words:
                    name_match = True

            if name_match:
                return contact, ce.email
            best_match = (contact, ce.email)

        if header_name:
            words = [w for w in header_name.lower().replace('.', ' ').split() if len(w) > 2]
            for word in words:
                qs = Contact.objects.filter(name__icontains=word)
                if qs.exists():
                    contact = qs.first()
                    primary = contact.primary_email
                    if primary:
                        return contact, primary.email
                    first_ce = ContactEmail.objects.filter(contact=contact).first()
                    if first_ce:
                        return contact, first_ce.email

        if best_match:
            return best_match
        return None, header_email
