import re
from typing import List, Optional, Union

import bleach


_CLEAN_NUMBER_RE = re.compile(r'[\xa0\u202f\u2009\u00a0\u2007 ]')


def sanitize_id(value: Union[str, int]) -> int:
    """Очищает ID от неразрывных пробелов. '7\\xa0585' -> 7585."""
    if isinstance(value, int):
        return value
    cleaned = _CLEAN_NUMBER_RE.sub('', str(value)).strip()
    return int(cleaned)


def sanitize_id_list(values: List[str]) -> List[int]:
    """Очищает список ID-строк, возвращает список int."""
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
    'ol', 'strong', 'ul', 'p', 'br', 'div', 'span',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'img', 'hr',
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


def clean_email_html(html_content: str) -> str:
    """Очистка HTML от опасных тегов и скриптов."""
    if not html_content:
        return ''
    return bleach.clean(
        html_content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True,
    )


_EMAIL_IN_ANGLE_RE = re.compile(r'<([^>]+@[^>]+)>')
_EMAIL_STANDALONE_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

# Транслитерация кириллицы → латиница (для поиска контактов по псевдонимам)
_CYR_TO_LAT = str.maketrans({
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd',
    'е': 'e', 'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i',
    'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
    'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
    'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch',
    'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
})


def _translit(text: str) -> str:
    """Переводит кириллицу в латиницу для поиска по псевдонимам контактов."""
    return text.lower().translate(_CYR_TO_LAT)


def _get_contact_email(contact):
    """Возвращает primary email контакта или первый email."""
    primary = contact.primary_email
    if primary:
        return primary.email
    first = contact.emails.first()
    if first:
        return first.email
    return None


def _is_clean_word(word: str) -> bool:
    """Проверяет, что слово подходит для поиска контакта."""
    if len(word) <= 2:
        return False
    if any(c in word for c in '<>{}[]()'):
        return False
    if not any(c.isalpha() for c in word):
        return False
    return True


def _find_contact_by_word(word: str):
    """
    Ищет контакт по одному слову: по имени контакта, по email контакта,
    с транслитерацией кириллицы. Возвращает email контакта или None.
    """
    from .models import Contact, ContactEmail

    # 1. Поиск по имени контакта
    contact = Contact.objects.filter(is_active=True, name__icontains=word).first()
    if contact:
        result = _get_contact_email(contact)
        if result:
            return result

    # 2. Поиск по email контакта (псевдоним в локальной части)
    ce = ContactEmail.objects.filter(
        email__icontains=word, contact__is_active=True
    ).select_related('contact').first()
    if ce:
        result = _get_contact_email(ce.contact)
        if result:
            return result

    # 3. Транслитерация (кириллица → латиница)
    translit = _translit(word)
    if translit != word.lower():
        contact = Contact.objects.filter(is_active=True, name__icontains=translit).first()
        if contact:
            result = _get_contact_email(contact)
            if result:
                return result
        ce = ContactEmail.objects.filter(
            email__icontains=translit, contact__is_active=True
        ).select_related('contact').first()
        if ce:
            result = _get_contact_email(ce.contact)
            if result:
                return result

    return None


_NAME_ONLY_RE = re.compile(r'^(.*?)\s*<[^>]+@[^>]+>\s*$')


def _search_contact(text: str):
    """
    Ищет контакт по тексту (полное имя или фрагмент).
    Сначала пробует весь текст, затем отдельные слова.
    """
    if not text:
        return None

    # Извлекаем имя из "Name <email>" → "Name"
    m = _NAME_ONLY_RE.match(text.strip())
    search_text = m.group(1).strip() if m else text.strip()

    if not _is_clean_word(search_text):
        # Если имя не подходит для поиска — попробовать исходный текст
        if not _is_clean_word(text.strip()):
            return None
        search_text = text.strip()

    # Сначала целый текст
    result = _find_contact_by_word(search_text)
    if result:
        return result

    # Затем по отдельным словам
    for word in search_text.lower().split():
        if _is_clean_word(word):
            result = _find_contact_by_word(word)
            if result:
                return result

    return None


def extract_email_address(text: str) -> Optional[str]:
    """Извлекает первый email из строки. Поддерживает 'Name <email>' и bare email."""
    if not text:
        return None
    text = text.strip()
    if not text:
        return None
    m = _EMAIL_IN_ANGLE_RE.search(text)
    if m:
        return m.group(1).strip()
    for part in (p.strip() for p in text.split(',') if p.strip()):
        if _EMAIL_STANDALONE_RE.match(part):
            return part
    return None


def extract_all_email_addresses(text: str) -> List[str]:
    """Извлекает все email-адреса из строки."""
    if not text:
        return []
    text = text.strip()
    if not text:
        return []
    results = []
    for m in _EMAIL_IN_ANGLE_RE.finditer(text):
        addr = m.group(1).strip()
        if addr not in results:
            results.append(addr)
    for part in text.split(','):
        part = part.strip()
        if _EMAIL_STANDALONE_RE.match(part) and part not in results:
            results.append(part)
    return results


def resolve_sender_to_email(sender: str, sender_name: str = '') -> str:
    """
    Резолвит отправителя в email.
    1) Если передан sender_name — ищет контакт по имени, возвращает его primary email.
    2) Если содержит email — извлекает.
    3) Ищет в Contact по имени.
    4) Ищет в других письмах с тем же отправителем.
    """
    from .models import Contact, ContactEmail

    # Шаг 1: поиск по имени отправителя (sender_name из заголовка)
    if sender_name:
        result = _search_contact(sender_name)
        if result:
            return result

    if not sender:
        return ''

    sender_clean = sender.strip()

    # Шаг 2: поиск контакта по имени из sender (корректирует неверные email
    # вида "Innokentiy Andreev <bezborodov.s@cimrus.com>")
    result = _search_contact(sender_clean)
    if result:
        return result

    # Шаг 3: извлечение email (если имя не найдено среди контактов)
    email = extract_email_address(sender)
    if email:
        return email

    from Emails.models import Email as EmailModel
    similar = EmailModel.objects.filter(
        sender__icontains=sender_clean
    ).exclude(
        sender=sender_clean
    ).exclude(
        sender__regex=r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    ).values_list('sender', flat=True)[:10]

    for s in similar:
        found = extract_email_address(s)
        if found:
            return found

    return ''


import hashlib

_AVATAR_COLORS = [
    '#e53935', '#d81b60', '#8e24aa', '#5e35b1',
    '#3949ab', '#1e88e5', '#039be5', '#00acc1',
    '#00897b', '#43a047', '#7cb342', '#c0ca33',
    '#fdd835', '#ffb300', '#fb8c00', '#f4511e',
    '#6d4c41', '#757575', '#546e7a',
]


def get_avatar_data(name_or_email: str) -> dict:
    """Генерирует данные для аватара-инициала."""
    if not name_or_email:
        name_or_email = '?'

    display = name_or_email.strip()
    if '<' in display and '>' in display:
        display = display.split('<')[0].strip().strip('"\'')
    if not display and '@' in name_or_email:
        display = name_or_email.split('@')[0]
    if not display:
        display = '?'

    words = display.split()
    if len(words) >= 2:
        initials = (words[0][0] + words[1][0]).upper()
    elif len(words) == 1 and len(words[0]) >= 2:
        initials = words[0][:2].upper()
    else:
        initials = display[:2].upper()

    h = int(hashlib.md5(name_or_email.encode('utf-8')).hexdigest(), 16)
    color = _AVATAR_COLORS[h % len(_AVATAR_COLORS)]

    return {'initials': initials, 'color': color}
