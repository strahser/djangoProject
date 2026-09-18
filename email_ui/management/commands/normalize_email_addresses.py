"""Замена алиасов на твёрдую почту (единое состояние истины).

Что делает:
- sender: canonical bare email (lower). Обрезки вида 'Name <localpart'
  (старый split('@')[0]) восстанавливаются через карту localpart->email,
  построенную из хороших строк и ContactEmail. Имена без @ НЕ трогаем
  (не выдумываем адреса — см. resolve_sender_to_email).
- receiver/cc: canonical comma-списки bare email. Поля целиком без @
  не затираем (оставляем как есть для ручного разбора).

Запуск:
    python manage.py normalize_email_addresses --dry-run [--limit N]
    python manage.py normalize_email_addresses --apply [--limit N]
"""
from django.core.management.base import BaseCommand
from Emails.models import Email
from email_ui.models import ContactEmail
from email_ui.utils import canonical_email, canonical_address_list, canonical_localpart


class Command(BaseCommand):
    help = 'Заменяет алиасы/обрезки на каноническую почту (см. docstring)'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Записать изменения (без флага — dry-run)')
        parser.add_argument('--dry-run', action='store_true', help='Явный dry-run')
        parser.add_argument('--limit', type=int, default=0)

    def handle(self, *args, **options):
        apply = options['apply'] and not options['dry_run']
        limit = options['limit']

        # Карта localpart -> email из хороших данных (источник истины)
        local_map = {}
        for s in Email.objects.filter(sender__contains='@').values_list('sender', flat=True).distinct():
            c = canonical_email(s)
            if c:
                local_map.setdefault(c.split('@')[0], c)
        for ce in ContactEmail.objects.all():
            c = canonical_email(ce.email)
            if c:
                local_map.setdefault(c.split('@')[0], c)

        qs = Email.objects.all().order_by('pk')
        if limit:
            qs = qs[:limit]
        total = qs.count()

        n_sender_canon = n_sender_trunc = n_sender_skip = 0
        n_recv = n_cc = 0
        n_recv_skip = n_cc_skip = 0
        examples = []

        for em in qs.iterator():
            updates = {}

            # --- sender ---
            raw_sender = em.sender or ''
            canon = canonical_email(raw_sender)
            if canon and canon != raw_sender:
                updates['sender'] = canon
                n_sender_canon += 1
                if len(examples) < 10:
                    examples.append((em.pk, 'sender', raw_sender, canon))
            elif not canon and '<' in raw_sender:
                lp = canonical_localpart(raw_sender)
                full = local_map.get(lp)
                if full:
                    updates['sender'] = full
                    prefix = raw_sender.split('<')[0].strip().strip('"\' ')
                    if prefix and prefix != em.sender_name:
                        updates['sender_name'] = prefix
                    n_sender_trunc += 1
                    if len(examples) < 10:
                        examples.append((em.pk, 'sender', raw_sender, full))
                else:
                    n_sender_skip += 1
            elif not canon and raw_sender:
                n_sender_skip += 1

            # --- receiver (не затираем поля без @) ---
            if em.receiver and '@' in em.receiver:
                canon_r = canonical_address_list(em.receiver)
                if canon_r and canon_r != em.receiver:
                    updates['receiver'] = canon_r
                    n_recv += 1
            elif em.receiver:
                n_recv_skip += 1

            # --- cc ---
            if em.cc and '@' in em.cc:
                canon_c = canonical_address_list(em.cc)
                if canon_c and canon_c != em.cc:
                    updates['cc'] = canon_c
                    n_cc += 1
            elif em.cc:
                n_cc_skip += 1

            if updates and apply:
                Email.objects.filter(pk=em.pk).update(**updates)

        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(f'[{mode}] total={total}')
        self.stdout.write(f'  sender canonical-fix={n_sender_canon}')
        self.stdout.write(f'  sender trunc->solid={n_sender_trunc}')
        self.stdout.write(f'  sender skipped (name-only, вручную)={n_sender_skip}')
        self.stdout.write(f'  receiver normalized={n_recv} skipped-no-@={n_recv_skip}')
        self.stdout.write(f'  cc normalized={n_cc} skipped-no-@={n_cc_skip}')
        for pk, field, old, new in examples:
            self.stdout.write(f'  ex [{pk}] {field}: {old!r} -> {new!r}')
        if not apply:
            self.stdout.write(self.style.WARNING('DRY-RUN: изменения не записаны. Для записи: --apply'))
