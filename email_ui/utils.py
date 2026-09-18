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
    'font', 'u', 'pre', 'sub', 'sup',
]
_STYLE_ATTRS = ['class', 'style']
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title', 'target', 'style'],
    'img': ['src', 'alt', 'width', 'height', 'style'],
    'div': _STYLE_ATTRS,
    'span': _STYLE_ATTRS,
    'p': _STYLE_ATTRS,
    'li': _STYLE_ATTRS,
    'ul': _STYLE_ATTRS,
    'ol': _STYLE_ATTRS,
    'blockquote': _STYLE_ATTRS,
    'table': ['border', 'cellpadding', 'cellspacing', 'style'],
    'thead': _STYLE_ATTRS,
    'tbody': _STYLE_ATTRS,
    'tr': _STYLE_ATTRS,
    'td': ['colspan', 'rowspan', 'style'],
    'th': ['colspan', 'rowspan', 'style'],
    'h1': _STYLE_ATTRS,
    'h2': _STYLE_ATTRS,
    'h3': _STYLE_ATTRS,
    'h4': _STYLE_ATTRS,
    'h5': _STYLE_ATTRS,
    'h6': _STYLE_ATTRS,
    'font': ['color', 'face', 'size'],
    'pre': _STYLE_ATTRS,
}

ALLOWED_CSS_PROPERTIES = [
    'color', 'background-color',
    'font-family', 'font-size', 'font-weight', 'font-style',
    'text-decoration', 'text-decoration-color', 'text-decoration-style',
    'text-align', 'line-height', 'vertical-align', 'width',
]

_DANGEROUS_CSS_RE = re.compile(r'url\s*\(|expression\s*\(|behaviou?r\s*:|-moz-binding|javascript\s*:', re.IGNORECASE)

_ALLOWED_CSS_SET = frozenset(ALLOWED_CSS_PROPERTIES)
_SAFE_CSS_VALUE_RE = re.compile(r"[a-zA-Z0-9\s,#%().'\-_/]+")


def _filter_style_declarations(body: str) -> str:
    """Белый список CSS-деклараций без tinycss2: имя из ALLOWED + безопасное значение."""
    kept = []
    for decl in body.split(';'):
        decl = decl.strip()
        if not decl or ':' not in decl:
            continue
        prop, _, val = decl.partition(':')
        prop = prop.strip().lower()
        val = val.strip()
        if prop not in _ALLOWED_CSS_SET:
            continue
        if _DANGEROUS_CSS_RE.search(prop + ':' + val):
            continue
        if not val or not _SAFE_CSS_VALUE_RE.fullmatch(val):
            continue
        kept.append('%s: %s' % (prop, val))
    return '; '.join(kept)


def _clean_without_css_sanitizer(html_content: str) -> str:
    """Откат без tinycss2: прячем style в data-атрибут, чистим bleach, возвращаем проверенное."""
    styles = []

    def _pull(match):
        styles.append(match.group(2))
        return 'data-letter-style="%d"' % (len(styles) - 1)

    tmp = re.sub(r'style=(["\'])(.*?)\1', _pull, html_content, flags=re.IGNORECASE | re.DOTALL)
    attrs = dict(ALLOWED_ATTRIBUTES)
    attrs['*'] = ['data-letter-style']
    cleaned = bleach.clean(tmp, tags=ALLOWED_TAGS, attributes=attrs, strip=True)

    def _restore(match):
        filt = _filter_style_declarations(styles[int(match.group(1))])
        return 'style="%s"' % filt if filt else ''

    cleaned = re.sub(r'data-letter-style="(\d+)"', _restore, cleaned)
    return _scrub_dangerous_css(cleaned)


def _scrub_dangerous_css(html_content: str) -> str:
    """Вырезает опасные декларации из style-атрибутов (XSS через CSS).

    CSSSanitizer проверяет имена свойств, но значения типа url(javascript:...)
    отсекаем явно — для надёжности.
    """
    def _scrub_style(match):
        quote, body = match.group(1), match.group(2)
        kept = []
        for decl in body.split(';'):
            decl = decl.strip()
            if not decl or ':' not in decl:
                continue
            if _DANGEROUS_CSS_RE.search(decl):
                continue
            kept.append(decl)
        if not kept:
            return ''
        return 'style=%s%s%s' % (quote, '; '.join(kept), quote)
    return re.sub(r'style=(["\'])(.*?)\1', _scrub_style, html_content, flags=re.IGNORECASE | re.DOTALL)



_EMBEDDED_BLOCK_RE = re.compile(
    r'<(style|script|head)\b[^>]*>.*?</\1>',
    re.IGNORECASE | re.DOTALL,
)


def _strip_style_script_head(html_content):
    """Удаляет <style>, <script> и <head> целиком вместе с содержимым.

    bleach.clean удаляет тег <style>, но ОСТАВЛЯЕТ его текстовое содержимое
    (например "P {margin-top:0;margin-bottom:0;}") как видимый текст письма.
    Поэтому CSS/JS-блоки и head вырезаем заранее, целиком.
    """
    if not html_content:
        return html_content
    return _EMBEDDED_BLOCK_RE.sub('', html_content)


def clean_email_html(html_content: str) -> str:
    """Очистка HTML от опасных тегов и скриптов.

    Авторские стили переписки (цвет/заливка/шрифт) сохраняются через белый
    список CSS-свойств — ответы, выделенные цветом, остаются цветными.
    Без tinycss2 в окружении используется встроенный откат (_filter_style_declarations).
    """
    if not html_content:
        return ''
    html_content = _strip_style_script_head(html_content)
    try:
        from bleach.css_sanitizer import CSSSanitizer
        css = CSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPERTIES)
    except Exception:
        return _clean_without_css_sanitizer(html_content)
    cleaned = bleach.clean(
        html_content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        css_sanitizer=css,
        strip=True,
    )
    return _scrub_dangerous_css(cleaned)


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


_BODY_HEADER_PREFIXES = ('отправитель:', 'получатель:', 'дата:', 'тема письма:', 'вложения:')

# Технические заголовки в PLAIN-тексте (прелюдия, которую IMAP-парсер пишет
# в начало HTML-файла и которая через html_body_to_text утекает в body_text):
# «Отправитель:A Получатель:B Дата:C Тема Письма:D Вложения: <тело>».
# Порядок прелюды фиксирован, значения могут содержать двоеточия
# (время «10:00», «GMT+03:00», URL), поэтому значения отрезаем не по первому
# двоеточию, а по следующей ожидаемой метке.
_TECH_HEADER_ORDER = ('отправитель', 'получатель', 'дата', 'тема письма', 'вложения')
_TECH_HEADER_LABELS = _TECH_HEADER_ORDER + ('тема', 'кому', 'from', 'to', 'date', 'subject')


def _tech_label_re(labels):
    return r'(?:' + '|'.join(labels) + r')'


_LEAD_TECH_RE = re.compile(
    r'^' + _tech_label_re(_TECH_HEADER_LABELS) + r'\s*:', re.IGNORECASE)
_NEXT_TECH_RE = re.compile(
    r'\s' + _tech_label_re(_TECH_HEADER_LABELS) + r'\s*:', re.IGNORECASE)

# Запасной поиск следующей метки режет только в ближнем окне: значение
# одиночного заголовка короткое (почта, дата), а прыжок через весь тред
# (напр. до «Темы:» в старой цитате) съедал бы тело. Для последнего
# заголовка («Вложения» со списком файлов) запасной поиск запрещён вовсе:
# границу значения в plain-тексте не восстановить, имена режем точным
# совпадением через attachments.
_TECH_FALLBACK_WINDOW = 80


def _next_label_within(text, start, window=_TECH_FALLBACK_WINDOW):
    nxt = _NEXT_TECH_RE.search(text, start)
    if nxt is not None and nxt.start() - start <= window:
        return nxt
    return None

# Префиксы пересылок/ответов в теме («Re: Re: …»): дубль темы в теле идёт
# уже без них, поэтому перед сравнением нормализуем.
_SUBJECT_PREFIX_RE = re.compile(r'^(?:re(?:\[\d+\])?|fw|fwd|пер)\s*:\s*', re.IGNORECASE)

# Заголовок цитаты в начале тела: «тема; 11.09.2026, 12:30, "Имя" <mail>:»
# или «On 11.09.2026, 12:30, Имя <mail>:». Требуется дата + почта в угловых
# скобках — иначе обычный текст, начинающийся с даты, не трогаем.
_QUOTE_HEAD_RE = re.compile(
    r'^[;,\s]*'
    r'(?:on\s+)?'
    r'(?:\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}|\d{4}-\d{1,2}-\d{1,2})'
    r'\s*,[^<>]*<[^<>]*@[^<>]*>\s*:',
    re.IGNORECASE)


def _normalize_subject(subject: str) -> str:
    """Тема без префиксов ответов/пересылок: «Re: Re: X» → «X»."""
    subj = re.sub(r'\s+', ' ', str(subject or '')).strip()
    while True:
        ns = _SUBJECT_PREFIX_RE.sub('', subj).strip()
        if ns == subj:
            return subj
        subj = ns


def strip_tech_headers(text: str, subject: str = '', attachments=()) -> str:
    """Убирает ведущую техническую прелюдию plain-текста письма.

    Два прохода:
    1) фиксированный порядок прелюды IMAP-парсера (значение — до следующей
       ожидаемой метки; если её нет и заголовок не последний — до любой
       следующей метки в ближнем окне (80 символов), иначе режется только
       метка; у последнего, «Вложений», значение — имена файлов, режется
       только метка, имена — точным совпадением);
    2) общий цикл по любым ведущим «метка:» (англ. From/To/…, одиночные).
    На последнем заголовке без продолжения режется только метка, остаток
    (это уже может быть тело) сохраняется, дальше — стоп.

    subject: дубль темы («Тема Письма:D» без «Вложений» дальше, в т.ч.
    «Re: D» в теме при «D» в теле) отрезается вместе с прилипшим артефактом
    старого парсера («D None <тело>»). Срабатывает, только если за дублем
    идёт разделитель/заголовок цитаты/конец — обычное тело, начинающееся
    теми же словами, не трогаем.
    attachments: имена файлов из «Вложений:» (границу с телом в plain-тексте
    не восстановить, поэтому известные имена режем точным совпадением).
    Хвостовые заголовки цитат («тема; дата, автор <mail>:»,
    «On date, author:») режутся всегда.
    """
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    # Проход 1: строгий порядок прелюды парсера.
    for pos, label in enumerate(_TECH_HEADER_ORDER):
        m = re.match(r'^' + re.escape(label) + r'\s*:', text, re.IGNORECASE)
        if not m:
            break
        rest_labels = _TECH_HEADER_ORDER[pos + 1:]
        cut = None
        if rest_labels:
            nxt = re.search(
                r'\s' + _tech_label_re(rest_labels) + r'\s*:', text[m.end():],
                re.IGNORECASE)
            if nxt is not None:
                cut = m.end() + nxt.start() + 1
        if cut is None:
            if rest_labels:
                # Не последний заголовок (напр. текст из БД без «Вложений»):
                # значение короткое — ищем любую следующую метку только
                # в ближнем окне, иначе режем только метку.
                nxt = _next_label_within(text, m.end())
                cut = (nxt.start() + 1) if nxt is not None else None
            # Последний («Вложения»): значение — имена файлов, в plain-тексте
            # границу не восстановить — режем только метку, имена снимет
            # точное совпадение через attachments ниже.
        if cut is None:
            text = text[m.end():].lstrip()
            break
        text = text[cut:].lstrip()
    # Проход 2: любые одиночные/переставленные ведущие метки.
    while True:
        m = _LEAD_TECH_RE.match(text)
        if not m:
            break
        nxt = _next_label_within(text, m.end())
        if not nxt:
            text = text[m.end():].lstrip()
            break
        text = text[nxt.start() + 1:].lstrip()
    # Имена вложений из «Вложений:» — точным совпадением с начала.
    if attachments:
        for _ in range(len(tuple(attachments)) + 2):
            stripped = False
            for fn in attachments:
                fn = re.sub(r'\s+', ' ', str(fn or '')).strip()
                if fn and text.startswith(fn):
                    text = re.sub(r'^[,;\s]+', '', text[len(fn):]).lstrip()
                    stripped = True
                    break
            if not stripped:
                break
    # Дубль темы: «Тема Письма:D» без «Вложений» дальше оставляет D в начале.
    # D заведомо не тело — оно уже показано полем «Тема». Режем, только если
    # за дублем идёт разделитель/заголовок цитаты/конец (иначе это может быть
    # обычное тело, начинающееся теми же словами, что тема).
    subj = _normalize_subject(subject)
    if subj and text.startswith(subj):
        rest = text[len(subj):]
        rest_stripped = rest.lstrip()
        if (not rest_stripped
                or rest_stripped.startswith((';', ',', ':', '—', '-', '–'))
                or rest_stripped == 'None'
                or rest_stripped.startswith('None ')
                or _QUOTE_HEAD_RE.match(rest_stripped)):
            text = re.sub(r'^[;,\s:—–-]+', '', rest).lstrip()
            if text == 'None' or text.startswith('None '):
                # Артефакт старого парсера («D None <тело>»).
                text = text[4:].lstrip()
    # Заголовки цитат вида «тема; дата, автор <mail>:» — в превью не нужны.
    for _ in range(5):
        m = _QUOTE_HEAD_RE.match(text)
        if not m:
            break
        text = text[m.end():].lstrip()
    return text

_BODY_SKIP_RES = [
    re.compile(r'^-{2,}\s*$'),         # разделитель --------
    re.compile(r'^\d{2}\.\d{2}\.\d{4}'),  # дата: 23.07.2026
]
_BODY_SIG_SEP_RE = re.compile(r'^--\s*$')   # сепаратор подписи


def _find_signature_table(soup):
    """Ищет последнюю таблицу с реквизитами компании — это подпись."""
    sig_keywords = ('cimrus', 'th-rus', 'strakhov',
                    'мобильный', 'mobile:', '+7 (', 'website:', 'сайт:')
    for table in reversed(soup.find_all('table')):
        text = table.get_text(strip=True).lower()
        if any(kw in text for kw in sig_keywords):
            return table
    return None


def _iter_body_elements(soup, signature_table):
    """Элементы, составляющие тело письма (та же эвристика, что сегментация).

    Пропускает заголовки, подпись, цитаты и зону подписи после '-- '.
    Единый источник истины для segment_letter_html и extract_body_head.
    """
    in_sig_zone = False
    for el in soup.find_all(['div', 'p', 'span']):
        text = el.get_text(strip=True)
        if not text:
            continue
        text_lower = text.lower()
        # Заголовки письма
        if any(text_lower.startswith(p) for p in _BODY_HEADER_PREFIXES):
            continue
        # Заголовки цитаты (Кому:, Тема:)
        if text_lower.startswith('кому:') or text_lower.startswith('тема:'):
            continue
        # Вход в зону подписи (всё после -- до следующего разделителя)
        if _BODY_SIG_SEP_RE.match(text):
            in_sig_zone = True
            continue
        # Разделители / даты (сброс зоны подписи)
        skip = False
        for pat in _BODY_SKIP_RES:
            if pat.match(text):
                skip = True
                in_sig_zone = False
                break
        if skip:
            continue
        # В зоне подписи — не тело
        if in_sig_zone:
            continue
        # Таблица подписи
        if signature_table:
            if signature_table in el.parents:
                continue
            if el.find_all('table') and any(t == signature_table for t in el.find_all('table')):
                continue
        yield el


_QUOTE_HEADER_PREFIXES = ('кому:', 'тема:')
_DATE_QUOTE_RE = re.compile(r'^\d{2}\.\d{2}\.\d{4}')


def segment_letter_html(html_content: str) -> str:
    """Раскладывает письмо на три карточки: шапка / сообщение / переписка+подпись.

    Классификация идёт по узлам верхнего уровня (та же эвристика, что
    _iter_body_elements, но позиционная, а не фильтрующая):
    - header: ведущие служебные строки (Отправитель/Получатель/Дата/...);
    - quote: blockquote, заголовки цитат (Кому:/Тема:/дата), разделители;
    - signature: всё после '-- ', таблица с реквизитами компании;
    - body: всё остальное — включая ответы, вкраплённые между цитатами.

    Разметка и авторские стили узлов сохраняются как есть — цвета ответов
    в переписке не затираются. Пустые зоны не рендерятся.
    """
    if not html_content:
        return ''
    from bs4 import BeautifulSoup, NavigableString
    import html as _html_module

    soup = BeautifulSoup(html_content, 'html.parser')
    root = soup.body if soup.body else soup
    signature_table = _find_signature_table(soup)

    zones = {'header': [], 'body': [], 'quote': [], 'signature': []}
    seen_body = False
    in_sig = False
    current = 'header'

    def _render(node):
        if isinstance(node, NavigableString):
            return _html_module.escape(str(node))
        return str(node)

    for node in list(root.contents):
        is_text = isinstance(node, NavigableString)
        text = (str(node).strip() if is_text
                else node.get_text(' ', strip=True).strip())
        if not text:
            # Пустые узлы (разрывы, div с одной картинкой/таблицей без текста) —
            # оставляем в текущей зоне: без них пропадают встроенные скриншоты.
            zones[current].append(_render(node))
            continue
        text_lower = text.lower()

        # Таблица подписи (сама или узел-контейнер).
        if not is_text and signature_table is not None and (
                node is signature_table or signature_table in node.descendants):
            in_sig = True
            current = 'signature'
            zones['signature'].append(_render(node))
            continue
        # Сепаратор подписи '-- ' — сам не показываем, дальше подпись.
        if _BODY_SIG_SEP_RE.match(text):
            in_sig = True
            current = 'signature'
            continue
        # Цитаты: blockquote, заголовки, разделители, строки с датой+адресом.
        is_sep = any(pat.match(text) for pat in _BODY_SKIP_RES)
        is_quote_head = text_lower.startswith(_QUOTE_HEADER_PREFIXES)
        is_date_quote = bool(_DATE_QUOTE_RE.match(text)) and (
            '@' in text or text.rstrip().endswith(':'))
        if (not is_text and getattr(node, 'name', '') == 'blockquote') or is_quote_head or is_date_quote:
            current = 'signature' if in_sig else 'quote'
            zones[current].append(_render(node))
            continue
        if is_sep:
            if in_sig:
                in_sig = False  # сброс зоны подписи, как в _iter_body_elements
            current = 'quote'
            zones['quote'].append(_render(node))
            continue
        # Служебные строки шапки — только ведущий блок.
        if any(text_lower.startswith(p) for p in _BODY_HEADER_PREFIXES):
            if not seen_body and not in_sig and current == 'header':
                zones['header'].append(_render(node))
            else:
                current = 'quote'
                zones['quote'].append(_render(node))
            continue
        # Остальное: подпись после '-- ' или тело (включая ответы между цитатами).
        if in_sig:
            current = 'signature'
            zones['signature'].append(_render(node))
        else:
            current = 'body'
            seen_body = True
            zones['body'].append(_render(node))

    parts = []
    if zones['header']:
        # Шапка дублирует заголовок окна письма — под экспандером, по умолчанию свернута.
        parts.append(
            '<details class="letter-section letter-header">'
            '<summary class="letter-section-title">Служебные поля</summary>'
            '<div class="letter-section-body">%s</div></details>' % ''.join(zones['header']))
    if zones['body']:
        parts.append(
            '<div class="letter-section letter-body">'
            '<div class="letter-section-title">Сообщение</div>'
            '<div class="letter-section-body">%s</div></div>' % ''.join(zones['body']))
    foot = list(zones['quote'])
    if zones['signature']:
        foot.append('<div class="letter-signature">%s</div>' % ''.join(zones['signature']))
    if foot:
        parts.append(
            '<div class="letter-section letter-footer">'
            '<div class="letter-section-title">Переписка и подпись</div>'
            '<div class="letter-section-body">%s</div></div>' % ''.join(foot))
    return ''.join(parts)


def highlight_email_body(html_content: str) -> str:
    """DEPRECATED: синяя перекраска тела удалена — затирала цвета ответов.

    Оставлена как тонкий переходник на segment_letter_html, чтобы не ломать
    внешние вызовы. Новые места должны вызывать segment_letter_html напрямую.
    """
    return segment_letter_html(html_content)


def extract_body_head(html_content: str, limit: int = 220, subject: str = '') -> str:
    """Голова тела письма: начало содержательного текста (та же эвристика, что у подсветки).

    Возвращает plain-text сниппет для превью в цепочках: без заголовков,
    дубля темы, заголовков цитат, подписей и цитат. Вложенные дубли
    (div > span с тем же текстом) отбрасываются.
    """
    if not html_content:
        return ''
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_content, 'html.parser')
    signature_table = _find_signature_table(soup)

    parts = []
    total = 0
    for el in _iter_body_elements(soup, signature_table):
        text = re.sub(r'\s+', ' ', el.get_text(' ', strip=True)).strip()
        if not text:
            continue
        # Вложенный дубль: текст уже покрыт ранее собранным (родитель/потомок).
        if any(text in p or p in text and p != text for p in parts):
            # Оставляем более длинный вариант
            parts = [p for p in parts if not (p in text and p != text)]
            if any(text in p for p in parts):
                continue
        parts.append(text)
        total += len(text)
        if total >= limit * 3:
            break
    head = re.sub(r'\s+', ' ', ' '.join(parts)).strip()
    head = strip_tech_headers(head, subject)
    if len(head) > limit:
        head = head[:limit].rsplit(' ', 1)[0] + '…'
    return head


def email_body_head(email, limit: int = 220, _cache=None) -> str:
    """Голова тела письма по объекту Email (читает HTML-файл, '' если файла нет).

    _cache — опциональный dict для переиспользования в пределах одного запроса.
    """
    key = getattr(email, 'pk', None)
    if _cache is not None and key in _cache:
        return _cache[key]
    head = ''
    try:
        html_path = email.get_html_file_path()
    except Exception:
        html_path = None
    if html_path:
        import os
        if os.path.exists(html_path):
            raw = None
            for enc in ('utf-8', 'cp1251'):
                try:
                    with open(html_path, 'r', encoding=enc) as f:
                        raw = f.read()
                    break
                except (UnicodeDecodeError, OSError):
                    continue
            if raw:
                try:
                    head = extract_body_head(
                        raw, limit, getattr(email, 'subject', ''))
                except Exception:
                    head = ''
    if _cache is not None and key is not None:
        _cache[key] = head
    return head


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


# ==================== Каноникализация email (единое состояние истины) ====================

_EMAIL_FIND_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')


def canonical_email(raw: str) -> str:
    """Приводит любое представление адреса к твёрдой почте: lower + bare email.

    'Murat Gurtekin <MURAT.G@cimrus.com>' -> 'murat.g@cimrus.com'
    '  Strakhov.S@Cimrus.Com.  ' -> 'strakhov.s@cimrus.com'
    'Vladimir Shivakov' -> '' (адреса нет — не выдумываем)
    """
    if not raw:
        return ''
    text = str(raw).strip().strip('<>').strip()
    if not text:
        return ''
    m = _EMAIL_IN_ANGLE_RE.search(text)
    if m:
        cand = m.group(1).strip().rstrip('.').lower()
        if _EMAIL_STANDALONE_RE.match(cand):
            return cand
    found = _EMAIL_FIND_RE.findall(text)
    if found:
        cand = found[0].rstrip('.').lower()
        if _EMAIL_STANDALONE_RE.match(cand):
            return cand
    cand = text.rstrip('.').lower()
    if _EMAIL_STANDALONE_RE.match(cand):
        return cand
    return ''


def canonical_address_list(raw: str) -> str:
    """Каноникализирует список адресов через запятую/точку с запятой.

    'A <a@x.ru>, BAD, b@y.ru; a@x.ru' -> 'a@x.ru, b@y.ru'
    Мусор без @ выбрасывается (не выдумываем адреса).
    """
    if not raw:
        return ''
    text = str(raw).replace(';', ',')
    seen = set()
    out = []
    for part in (p.strip() for p in text.split(',') if p.strip()):
        addr = canonical_email(part)
        if addr and addr not in seen:
            seen.add(addr)
            out.append(addr)
    return ', '.join(out)


def canonical_localpart(raw: str) -> str:
    """Возвращает локальную часть для сопоставления обрезанных алиасов.

    'Murat Gurtekin <murat.g' -> 'murat.g' (обрезок после split('@')[0])
    '"Sergey Dobosh" <drobosh.s' -> 'drobosh.s'
    """
    if not raw:
        return ''
    text = str(raw).strip()
    m = re.search(r'<([^<>@]+)\s*$', text)
    if m:
        return m.group(1).strip().strip('"\' ').lower()
    if '@' not in text and '<' not in text:
        cand = text.strip().strip('"\' ').lower()
        if cand and ' ' not in cand and len(cand) <= 64:
            return cand
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
