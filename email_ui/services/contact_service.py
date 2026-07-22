import logging
from typing import List, Optional, Tuple

from django.db.models import Q

from Emails.models import Email
from email_ui.models import Contact, ContactEmail

logger = logging.getLogger(__name__)


class ContactService:
    """
    Service for managing contacts and auto-extracting them from emails.
    """

    @staticmethod
    def extract_from_email(email: Email) -> Optional[Contact]:
        """
        Extract or update a contact from an email's sender.
        Returns existing or newly created Contact.
        """
        sender_raw = email.sender
        if not sender_raw:
            return None

        # Try to parse "Name <email>" format
        name, addr = ContactService._parse_sender(sender_raw)

        if not addr:
            return None

        # Try to find existing contact by email
        contact_email = ContactEmail.objects.filter(email__iexact=addr).first()
        if contact_email:
            contact = contact_email.contact
            # Update name if not set
            if name and not contact.name:
                contact.name = name
                contact.save(update_fields=['name'])
            return contact

        # Create new contact
        contact = Contact.objects.create(name=name or addr.split('@')[0])
        ContactEmail.objects.create(
            contact=contact,
            email=addr,
            is_primary=True,
            label='work',
        )
        logger.info(f'Created new contact from email: {name} <{addr}>')
        return contact

    @staticmethod
    def _parse_sender(sender: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse sender string into name and email address."""
        import re

        # Pattern: "Name <email>"
        match = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>', sender)
        if match:
            name = match.group(1).strip() or None
            email = match.group(2).strip()
            return name, email

        # Pattern: just email
        if '@' in sender:
            return None, sender.strip()

        # Just a name
        return sender.strip(), None

    @staticmethod
    def extract_from_receiver(email: Email) -> List[Contact]:
        """Extract contacts from receiver field (multiple addresses)."""
        contacts = []
        if email.receiver:
            receivers = email.receiver.split(',')
            for rec in receivers:
                rec = rec.strip()
                if rec:
                    contact_email = ContactEmail.objects.filter(email__iexact=rec).first()
                    if contact_email:
                        contacts.append(contact_email.contact)
        return contacts

    @staticmethod
    def get_or_create_contact(name: str, email_addr: str) -> Contact:
        """Get existing contact or create new one."""
        if email_addr:
            contact_email = ContactEmail.objects.filter(email__iexact=email_addr).first()
            if contact_email:
                return contact_email.contact

        contact = Contact.objects.create(name=name or email_addr.split('@')[0])
        if email_addr:
            ContactEmail.objects.create(
                contact=contact,
                email=email_addr,
                is_primary=True,
            )
        return contact

    @staticmethod
    def search_contacts(query: str) -> List[Contact]:
        """Search contacts by name or email."""
        return Contact.objects.filter(
            Q(name__icontains=query) |
            Q(emails__email__icontains=query)
        ).distinct().order_by('name')[:20]

    @staticmethod
    def merge_contacts(source_id: int, target_id: int) -> Contact:
        """Merge two contacts, moving all emails from source to target."""
        source = Contact.objects.get(id=source_id)
        target = Contact.objects.get(id=target_id)

        # Move all emails to target
        for ce in ContactEmail.objects.filter(contact=source):
            ce.contact = target
            ce.save()

        # Move all email messages to target
        Email.objects.filter(contact=source).update(contact=target)

        # Copy notes if empty
        if source.notes and not target.notes:
            target.notes = source.notes

        # Copy phone if empty
        if source.phone and not target.phone:
            target.phone = source.phone

        target.save()
        source.delete()
        logger.info(f'Merged contact {source_id} into {target_id}')
        return target
