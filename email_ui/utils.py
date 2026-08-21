import re
from typing import List, Optional, Union

import bleach
from django.urls import reverse


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


_IMG_CID_SRC_RE = re.compile(
    r'(<img\b[^>]*?\bsrc\s*=\s*["\'])\s*cid:([^"\']+?)\s*(["\'])',
    re.IGNORECASE,
)


def _normalize_cid(value: str) -> str:
    """Нормализует Content-ID: снимает кавычки, угловые скобки, префикс cid:."""
    value = value.strip().strip('<>').strip()
    if value.lower().startswith('cid:'):
        value = value[4:]
    return value.strip().lower()


def resolve_inline_image_urls(email, html_content: str) -> str:
    """Заменяет src="cid:..." в теле письма на URL просмотра вложения.

    Изображения (скриншоты) сохраняются в папке письма вместе с вложениями,
    но content_id в БД обычно не хранится, поэтому:
    1) если у вложения заполнен content_id — ищем точное совпадение;
    2) иначе сопоставляем cid-ссылки по порядку с image-вложениями письма.
    """
    if not html_content or '<img' not in html_content.lower():
        return html_content

    attachments = list(email.attachments.all())

    by_cid = {}
    for att in attachments:
        if att.content_id:
            by_cid.setdefault(_normalize_cid(att.content_id), att)

    image_atts = [
        a for a in attachments
        if (a.content_type or '').lower().startswith('image/')
    ]
    used = set()

    def _pick(cid: str):
        att = by_cid.get(_normalize_cid(cid))
        if att is not None and att.pk not in used:
            used.add(att.pk)
            return att
        for a in image_atts:
            if a.pk not in used:
                used.add(a.pk)
                return a
        return None

    def _replace(match):
        att = _pick(match.group(2))
        if att is None:
            return match.group(0)
        url = reverse('email_ui:attachment_inline', args=[att.pk])
        return f'{match.group(1)}{url}{match.group(3)}'

    return _IMG_CID_SRC_RE.sub(_replace, html_content)


def highlight_email_body(html_content: str) -> str:
    """Парсит HTML письма, находит тело письма (текст после заголовков и до подписи)
    и выделяет текст синим цветом (#0d6efd) для контрастности.

    Пропускает:
    - Заголовки (Отправитель, Получатель, Дата, Тема Письма, Вложения)
    - Подпись (таблица с реквизитами компании в конце письма)
    - Блоки цитируемого текста: Кому, Тема, дата, разделители
    - Всё после '-- ' до следующего '----------------' (подпись в цитате)
    """
    if not html_content:
        return html_content

    from bs4 import BeautifulSoup
    import re as _re

    soup = BeautifulSoup(html_content, 'html.parser')

    signature_table = _find_signature_table(soup)

    header_prefixes = ('отправитель:', 'получатель:', 'дата:', 'тема письма:', 'вложения:')

    skip_re = [
        _re.compile(r'^-{2,}\s*$'),         # разделитель --------
        _re.compile(r'^\d{2}\.\d{2}\.\d{4}'),  # дата: 23.07.2026
    ]
    sig_sep_re = _re.compile(r'^--\s*$')   # сепаратор подписи

    in_sig_zone = False

    for el in soup.find_all(['div', 'p', 'span']):
        text = el.get_text(strip=True)
        if not text:
            continue

        text_lower = text.lower()

        # Заголовки письма
        if any(text_lower.startswith(p) for p in header_prefixes):
            continue

        # Заголовки цитаты (Кому:, Тема:)
        if text_lower.startswith('кому:') or text_lower.startswith('тема:'):
            continue

        # Вход в зону подписи (всё после -- до следующего разделителя)
        if sig_sep_re.match(text):
            in_sig_zone = True
            continue

        # Разделители / даты (сброс зоны подписи)
        skip = False
        for pat in skip_re:
            if pat.match(text):
                skip = True
                in_sig_zone = False
                break
        if skip:
            continue

        # В зоне подписи — не красим
        if in_sig_zone:
            continue

        # Таблица подписи
        if signature_table:
            if signature_table in el.parents:
                continue
            if el.find_all('table') and any(t == signature_table for t in el.find_all('table')):
                continue

        style = el.get('style', '')
        style = _re.sub(r'\bcolor\s*:\s*[^;]+;?\s*', '', style, flags=_re.IGNORECASE)
        el['style'] = f'color: #0d6efd; {style}'.strip('; ')

    return str(soup)


def _find_signature_table(soup):
    """Ищет последнюю таблицу с реквизитами компании — это подпись."""
    sig_keywords = ('cimrus', 'th-rus', 'strakhov',
                    'мобильный', 'mobile:', '+7 (', 'website:', 'сайт:')
    for table in reversed(soup.find_all('table')):
        text = table.get_text(strip=True).lower()
        if any(kw in text for kw in sig_keywords):
            return table
    return None


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
    Извлекает ЯВНЫЙ email-адрес из строки отправителя/получателя.

    НЕЧЁТКИЙ ПОИСК КОНТАКТОВ ЗАПРЕЩЁН. Адрес должен присутствовать
    непосредственно в самой строке (формат "Name <email>" или bare email).
    Если явного email в строке нет - возвращаем пустую строку, чтобы
    вызывающий код мог показать ОШИБКУ, а не отправлять письмо не тому
    адресату (подставляя email случайно подошедшего контакта).

    Безопасность сервиса ответов критична: подмена адресата недопустима.
    """
    if not sender:
        return ''
    sender_clean = sender.strip()
    email = extract_email_address(sender_clean)
    return email or ''


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
