import re
from typing import List, Union

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