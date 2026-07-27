import datetime
from typing import Optional

from imap_tools import MailBox

from Emails.models import Email
from Emails.ЕmailParser.EmailImapMessage import EmailBody
from email_ui.models import Contact, ContactEmail


class DbEmailImapMessageSerializer:
    """Сериализатор IMAP-сообщения в модель Email."""

    def __init__(self, email_type: str, link: str, msg):
        self.uid = msg.uid
        self.email_type = email_type
        self.subject = msg.subject or ''
        self.link = link
        self.body = EmailBody(msg).created_body
        self.sender_name, self.sender, self.sender_contact = self._extract_sender_parts(msg)
        self.receiver = msg.to_values
        self.cc = msg.cc_values
        self.email_stamp = msg.date
        self.creation_stamp = datetime.datetime.now()
        self.message_id = self._get_header(msg, 'Message-ID')
        self.in_reply_to = self._get_header(msg, 'In-Reply-To')
        self.references = self._get_header(msg, 'References')

    @staticmethod
    def _get_header(msg, header_name: str) -> str:
        try:
            values = msg.headers.get(header_name, [])
            if values:
                return values[0] if isinstance(values, (list, tuple)) else str(values)
        except Exception:
            pass
        return ''

    @staticmethod
    def _is_valid_name(name: str, email: str) -> bool:
        if not name:
            return False
        if name == email:
            return False
        if '@' in name:
            return False
        return True

    @staticmethod
    def _lookup_contact(header_name: str, header_email: str):
        """
        Ищет контакт: сначала по email (с проверкой имени), затем по имени.
        Возвращает (contact, corrected_email).
        """
        best_match = None

        # Шаг 1: поиск по email
        ce = ContactEmail.objects.filter(email__iexact=header_email).first()
        if ce:
            contact = ce.contact
            contact_name = (contact.name or '').lower().strip()
            header_name_lower = header_name.lower().strip() if header_name else ''

            # Проверяем совместимость имени: имя контакта должно быть похоже на имя из заголовка
            name_match = False
            if not header_name_lower or not contact_name:
                name_match = True
            elif contact_name in header_name_lower or header_name_lower in contact_name:
                name_match = True
            else:
                # Проверяем по словам: есть ли общие слова
                header_words = set(w for w in header_name_lower.replace('.', ' ').split() if len(w) > 1)
                contact_words = set(w for w in contact_name.replace('.', ' ').split() if len(w) > 1)
                if header_words & contact_words:
                    name_match = True

            if name_match:
                return contact, ce.email
            # Имя не совпало — запоминаем, но не возвращаем
            best_match = (contact, ce.email)

        # Шаг 2: поиск по имени (словами из заголовка)
        if header_name:
            header_words = [w for w in header_name.lower().replace('.', ' ').split() if len(w) > 2]
            for word in header_words:
                qs = Contact.objects.filter(name__icontains=word)
                if qs.exists():
                    contact = qs.first()
                    primary = contact.primary_email
                    if primary:
                        return contact, primary.email
                    first_ce = ContactEmail.objects.filter(contact=contact).first()
                    if first_ce:
                        return contact, first_ce.email

        # Шаг 3: fallback — возвращаем best_match если был
        if best_match:
            return best_match

        return None, header_email

    @staticmethod
    def _extract_sender_parts(msg):
        """
        Извлекает имя и email из заголовка From, корректирует email через базу контактов.
        Возвращает (sender_name, sender_email, contact_or_None).
        """
        from_values = msg.from_values
        if from_values is None:
            raw = (msg.from_ or '').strip()
            if not raw:
                return '', '', None
            if '<' in raw and '>' in raw:
                import re
                m = re.match(r'"?([^"<]*)"?\s*<([^>]+)>', raw)
                if m:
                    header_name = m.group(1).strip()
                    header_email = m.group(2).strip()
                else:
                    return '', raw, None
            else:
                return '', raw, None
            contact, corrected = DbEmailImapMessageSerializer._lookup_contact(header_name, header_email)
            return header_name, corrected, contact

        header_email = getattr(from_values, 'email', None)
        if header_email is None:
            header_email = getattr(from_values, 'addr_spec', None)
        if header_email is None:
            header_email = str(from_values)

        header_name = getattr(from_values, 'name', '') or ''
        if not DbEmailImapMessageSerializer._is_valid_name(header_name, header_email):
            header_name = ''

        contact, corrected = DbEmailImapMessageSerializer._lookup_contact(header_name, header_email)
        return header_name, corrected, contact

    def _format_address(self, addr) -> str:
        """Форматирует адрес как 'Name <email>' или просто email."""
        if addr is None:
            return ''
        email = getattr(addr, 'email', None)
        if email is None:
            email = getattr(addr, 'addr_spec', None)
        if email is None:
            email = str(addr)

        name = getattr(addr, 'name', '') or ''
        if DbEmailImapMessageSerializer._is_valid_name(name, email):
            return f'{name} <{email}>'
        return email

    def create_record(self) -> Email:
        receiver_str = ''
        if self.receiver:
            if len(self.receiver) == 1:
                receiver_str = self._format_address(self.receiver[0])
            else:
                receiver_str = ', '.join(
                    self._format_address(val) for val in self.receiver
                )

        cc_str = ''
        if self.cc:
            cc_str = ', '.join(
                self._format_address(val) for val in self.cc
            )

        folder = 'inbox' if self.email_type == 'IN' else 'sent'

        defaults = {
            'email_type': self.email_type,
            'subject': self.subject,
            'link': self.link,
            'sender': self.sender,
            'sender_name': self.sender_name,
            'receiver': receiver_str,
            'cc': cc_str or None,
            'email_stamp': self.email_stamp,
            'folder': folder,
            'message_id': self.message_id or None,
            'in_reply_to': self.in_reply_to or None,
            'references': self.references or None,
        }
        if self.sender_contact:
            defaults['contact'] = self.sender_contact

        email, created = Email.objects.get_or_create(
            uid=self.uid,
            defaults=defaults,
        )

        if not created:
            update_fields = []
            if email.sender != self.sender:
                email.sender = self.sender
                update_fields.append('sender')
            if email.sender_name != self.sender_name:
                email.sender_name = self.sender_name
                update_fields.append('sender_name')
            if email.receiver != receiver_str:
                email.receiver = receiver_str
                update_fields.append('receiver')
            if cc_str and email.cc != cc_str:
                email.cc = cc_str
                update_fields.append('cc')
            if self.message_id and email.message_id != self.message_id:
                email.message_id = self.message_id
                update_fields.append('message_id')
            if self.sender_contact and email.contact != self.sender_contact:
                email.contact = self.sender_contact
                update_fields.append('contact')
            if update_fields:
                email.save(update_fields=update_fields)

        return email
