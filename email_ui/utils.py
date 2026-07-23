import re
from typing import List, Optional, Union

import bleach

# Compiled regex to strip non-breaking spaces and formatting from number strings
_CLEAN_NUMBER_RE = re.compile(r'[\xa0\u202f\u2009\u00a0\u2007 ]')


def sanitize_id(value: Union[str, int]) -> int:
    """
    Sanitize an ID value that may contain non-breaking spaces or other formatting.
    E.g. '7\u00a0585' -> 7585
    """
    if isinstance(value, int):
        return value
    cleaned = _CLEAN_NUMBER_RE.sub('', str(value)).strip()
    return int(cleaned)


def sanitize_id_list(values: List[str]) -> List[int]:
    """
    Sanitize a list of ID strings, removing all non-breaking spaces and formatting.
    Returns list of clean integers.
    """
    result = []
    for v in values:
        v = v.strip()
        if not v:
            continue
        cleaned = _CLEAN_NUMBER_RE.sub('', v)
        try:
            result.append(int(cleaned))
        except (ValueError, TypeError):
            continue
    return result


ALLOWED_TAGS = [
    'a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em', 'i', 'li',
    'ol', 'strong', 'ul', 'p', 'br', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'img'
]
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title', 'target'],
    'img': ['src', 'alt', 'width', 'height'],
    'div': ['class', 'style'],
    'span': ['class', 'style'],
    'p': ['class', 'style'],
    'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan'],
    'table': ['border', 'cellpadding', 'cellspacing'],
}

def clean_email_html(html_content):
    """Очистка HTML от опасных тегов и скриптов."""
    return bleach.clean(html_content, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)


_EMAIL_IN_ANGLE_RE = re.compile(r'<([^>]+@[^>]+)>')
_EMAIL_STANDALONE_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


def extract_email_address(text: str) -> Optional[str]:
    """
    Extract a valid email address from a string.
    Handles formats:
      - "Name" <email@example.com>
      - Name <email@example.com>
      - email@example.com
      - Multiple comma-separated addresses
    Returns the first valid email found, or None.
    """
    if not text:
        return None
    text = text.strip()
    if not text:
        return None

    m = _EMAIL_IN_ANGLE_RE.search(text)
    if m:
        return m.group(1).strip()

    parts = [p.strip() for p in text.split(',') if p.strip()]
    for part in parts:
        if _EMAIL_STANDALONE_RE.match(part):
            return part

    return None


def extract_all_email_addresses(text: str) -> List[str]:
    """
    Extract all email addresses from a string (possibly comma-separated).
    Handles both <email> and bare email formats.
    """
    if not text:
        return []
    text = text.strip()
    if not text:
        return []

    results = []
    for m in _EMAIL_IN_ANGLE_RE.finditer(text):
        results.append(m.group(1).strip())

    for part in text.split(','):
        part = part.strip()
        if _EMAIL_STANDALONE_RE.match(part) and part not in results:
            results.append(part)

    return results


def resolve_sender_to_email(sender: str) -> str:
    """
    Resolve a sender string to an email address.
    If the sender string contains an email, extract it.
    If it's just a name, try to look up the Contact model.
    If still not found, search other emails where the same sender
    appears with an email in angle brackets (e.g. "Name <email>").
    """
    if not sender:
        return ''

    email = extract_email_address(sender)
    if email:
        return email

    from .models import Contact, ContactEmail

    contacts = Contact.objects.filter(is_active=True, name__icontains=sender.strip())
    for contact in contacts:
        primary = contact.primary_email
        if primary:
            return primary.email
        first = contact.emails.first()
        if first:
            return first.email

    words = sender.strip().lower().split()
    if words:
        for word in words:
            if len(word) > 2:
                contacts = Contact.objects.filter(is_active=True, name__icontains=word)
                for contact in contacts:
                    primary = contact.primary_email
                    if primary:
                        return primary.email
                    first = contact.emails.first()
                    if first:
                        return first.email

    from Emails.models import Email as EmailModel
    similar = EmailModel.objects.filter(
        sender__icontains=sender.strip()
    ).exclude(
        sender=sender.strip()
    ).exclude(
        sender__regex=r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    ).values_list('sender', flat=True)[:10]
    for s in similar:
        found = extract_email_address(s)
        if found:
            return found

    return ''