import hashlib
import re

from django import template

register = template.Library()

_AVATAR_COLORS = [
    '#e53935', '#d81b60', '#8e24aa', '#5e35b1',
    '#3949ab', '#1e88e5', '#039be5', '#00acc1',
    '#00897b', '#43a047', '#7cb342', '#c0ca33',
    '#fdd835', '#ffb300', '#fb8c00', '#f4511e',
    '#6d4c41', '#757575', '#546e7a',
]


def _get_avatar_data(name_or_email):
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


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def avatar_initials(name_or_email):
    return _get_avatar_data(name_or_email or '')['initials']


@register.filter
def avatar_color(name_or_email):
    return _get_avatar_data(name_or_email or '')['color']


@register.filter
def truncate_filename(filename, length=18):
    if not filename:
        return ''
    if len(filename) <= length:
        return filename
    name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
    max_name = length - len(ext) - 1
    if max_name < 3:
        return filename[:length] + '\u2026'
    return name[:max_name] + '\u2026.' + ext


@register.filter
def recipient_name(recipients):
    """
    LEGACY. Оставлен для совместимости, новые места используют canon_email(s).
    """
    if not recipients:
        return ''
    parts = []
    for part in recipients.split(','):
        part = part.strip()
        if not part:
            continue
        # Name <email> → Name
        if '<' in part and '>' in part:
            name = part.split('<')[0].strip().strip('"\' ')
        else:
            # Пытаемся отделить email в конце: 'Name email@domain'
            name = part
            if '@' in part:
                # Ищем последнее слово, содержащее @
                words = part.rsplit(None, 1)
                if len(words) == 2 and '@' in words[1]:
                    name = words[0]
        if name:
            parts.append(name)
    return ', '.join(parts) if parts else recipients[:50]


# ==================== SRP-блок показа почты: ТОЛЬКО твёрдая почта ====================
# Единственное место, решающее как отображать адреса во всех шаблонах
# (список, деталка, модалка, тред, контакты, подсказки пикера — через views).
# Битые алиасы вида 'Name <localpart' без @ превращаются в пусто, а не в мусор.

@register.filter
def canon_email(value):
    """Одиночное поле (sender): твёрдая bare-почта или пусто."""
    from email_ui.utils import canonical_email
    return canonical_email(value or '')


@register.filter
def canon_emails(value):
    """Список через запятую (receiver/cc): только твёрдые почты."""
    from email_ui.utils import canonical_address_list
    return canonical_address_list(value or '')


@register.filter
def body_preview(value, length=120):
    """Первые символы содержания письма для показа под темой.

    Технические заголовки прелюды («Отправитель:… Вложения:») вырезаются —
    иначе в списке вместо тела светятся служебные поля. Схлопывает
    пробелы/переносы, обрезает до length символов (по умолчанию 120 —
    примерно две строки превью). Границы 40..300, мусор — в ''.
    """
    return _truncate_preview(_clean_preview_text(value), length)


@register.filter
def email_preview(email, length=120):
    """Превью тела письма по объекту: как body_preview, плюс вырезается
    дубль темы («Re: X» в теме при «X; дата, автор:» в теле), имена вложений
    и заголовки цитат — начало показывает собственно тело («Добрый день, …»).
    Вложения уже подгружены списком (prefetch), отдельных запросов нет."""
    body = getattr(email, 'body_text', '') or ''
    subject = getattr(email, 'subject', '') or ''
    try:
        att_manager = getattr(email, 'attachments', None)
        attachments = [a.filename for a in att_manager.all()] if att_manager else []
    except Exception:
        attachments = []
    return _truncate_preview(_clean_preview_text(body, subject, attachments), length)


def _clean_preview_text(value, subject='', attachments=()):
    from email_ui.utils import strip_tech_headers
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return strip_tech_headers(text, subject, attachments)


def _truncate_preview(text, length):
    from email_ui.models import EmailViewSettings
    try:
        length = int(length)
    except (TypeError, ValueError):
        length = EmailViewSettings.DEFAULT_PREVIEW_LENGTH
    length = max(
        EmailViewSettings.MIN_PREVIEW_LENGTH,
        min(EmailViewSettings.MAX_PREVIEW_LENGTH, length),
    )
    if len(text) <= length:
        return text
    return text[:length].rstrip() + '…'
