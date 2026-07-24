import re
from django.core.management.base import BaseCommand
from django.db.models import Q
from Emails.models import Email
from email_ui.models import ContactEmail

_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
_EMAIL_IN_ANGLE_RE = re.compile(r'<([^>]+@[^>]+)>')
_NAME_IN_QUOTES_RE = re.compile(r'^["\u00AB]([^"\u00BB]+)["\u00BB]\s*$')
_STANDALONE_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


class Command(BaseCommand):
    help = 'Fixes display-name-only sender/receiver by building a name->email map from existing data'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limit', type=int, default=0)

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        self.stdout.write('Step 1: Building name -> email mapping...')

        name_to_email = {}

        contact_emails = ContactEmail.objects.select_related('contact').all()
        for ce in contact_emails:
            login = (ce.contact.name or '').lower().strip()
            if login and login not in name_to_email:
                name_to_email[login] = ce.email

        self.stdout.write(f'  ContactEmail logins: {len(name_to_email)}')

        emails_with_at = Email.objects.filter(
            Q(sender__regex=r'@') | Q(receiver__regex=r'@')
        ).iterator()

        count = 0
        for em in emails_with_at:
            for field_val in [em.sender, em.receiver, em.cc or '']:
                if not field_val:
                    continue
                for part in [p.strip() for p in field_val.split(',') if p.strip()]:
                    email_addr = None
                    display_name = None

                    m = _EMAIL_IN_ANGLE_RE.search(part)
                    if m:
                        email_addr = m.group(1).strip()
                        display_name = part[:m.start()].strip().strip('" \'')
                    elif _STANDALONE_EMAIL_RE.match(part):
                        email_addr = part
                        login = part.split('@')[0].lower().strip()
                        if login not in name_to_email:
                            name_to_email[login] = email_addr
                    else:
                        continue

                    if email_addr and display_name:
                        key = display_name.lower().strip()
                        if key and key not in name_to_email:
                            name_to_email[key] = email_addr
                            count += 1

        self.stdout.write(f'  Name->email mappings from fields: {count}')

        all_keys = list(name_to_email.keys())
        all_keys.sort(key=len, reverse=True)
        name_to_email_sorted = {k: name_to_email[k] for k in all_keys}

        self.stdout.write(f'  Total mapping entries: {len(name_to_email_sorted)}')

        self.stdout.write('Step 2: Processing emails without @ in sender/receiver...')

        q_no_at = Q(sender__isnull=True) | Q(sender='') | ~Q(sender__regex=r'@')
        q_no_at_r = Q(receiver__isnull=True) | Q(receiver='') | ~Q(receiver__regex=r'@')

        qs = Email.objects.filter(q_no_at | q_no_at_r).order_by('pk')
        if limit:
            qs = qs[:limit]

        fixed_sender = 0
        fixed_receiver = 0
        unchanged = 0

        for em in qs:
            new_sender = self._fix_field(em.sender, name_to_email_sorted)
            new_receiver = self._fix_field(em.receiver, name_to_email_sorted)

            sender_changed = new_sender != em.sender
            receiver_changed = new_receiver != em.receiver

            if sender_changed:
                fixed_sender += 1
                if not dry_run:
                    em.sender = new_sender

            if receiver_changed:
                fixed_receiver += 1
                if not dry_run:
                    em.receiver = new_receiver

            if not dry_run and (sender_changed or receiver_changed):
                em.save(update_fields=['sender', 'receiver'])
            else:
                unchanged += 1

        self.stdout.write(self.style.SUCCESS(
            f'{"[DRY RUN] " if dry_run else ""}'
            f'Fixed: sender={fixed_sender}, receiver={fixed_receiver}, '
            f'total processed={fixed_sender + fixed_receiver + unchanged}'
        ))

    def _fix_field(self, value, name_map):
        if not value:
            return value

        parts = [p.strip() for p in value.split(',') if p.strip()]
        fixed_parts = []
        for part in parts:
            fixed_parts.append(self._fix_single(part, name_map))

        return ', '.join(fixed_parts)

    def _fix_single(self, text, name_map):
        text = text.strip()
        if not text:
            return text

        m = _EMAIL_IN_ANGLE_RE.search(text)
        if m:
            return text

        if _STANDALONE_EMAIL_RE.match(text):
            return text

        emails_found = _EMAIL_RE.findall(text)
        if emails_found:
            name = text.split('<')[0].strip().strip('" \'')
            for e in emails_found:
                name = name.replace(e, '').strip()
            return f'{name} <{emails_found[0]}>' if name else emails_found[0]

        key = text.lower().strip()
        if key in name_map:
            return f'{text} <{name_map[key]}>'

        words = key.split()
        if len(words) >= 2:
            for wk, wv in name_map.items():
                if all(w in wk for w in words):
                    return f'{text} <{wv}>'

        return text
