import hashlib

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
