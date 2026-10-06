"""Блок 25: токены/Q-объекты/фильтр списка писем (вынесено из views.py 1:1)."""

import re

from django.db.models import Q
from django.db.models.functions import Coalesce, TruncDate

from email_ui.utils import extract_all_email_addresses


def _split_tokens(raw):
    """Делит мульти-ввод почты на токены (запятая/точка с запятой)."""
    if not raw:
        return []
    return [t.strip() for t in str(raw).replace(';', ',').split(',') if t.strip()]


# Мусор, который прилипает к адресу при копировании из письма: «Имя <a@b.ru>»,
# «"a@b.ru".», «a@b.ru,» — это всё один и тот же адрес, а в письме он хранится
# как bare-адрес без скобок, кавычек и точек. Без нормализации такие запросы
# молча давали «Нет писем».
_ADDRESS_EDGE_JUNK = ' \t\r\n<>"\'«»,;:.'

# Адрес внутри произвольного текста (регистр не важен — его решает _ci_variants).
_EMAIL_IN_TEXT_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')


def _token_addresses(raw):
    """Адреса внутри одного токена без обрамляющего мусора.

    'kunaev@isetgroup.ru.'         -> ['kunaev@isetgroup.ru']
    'Кунаев <kunaev@isetgroup.ru>' -> ['kunaev@isetgroup.ru']
    'a@b.ru c@d.ru'                -> ['a@b.ru', 'c@d.ru']
    'Кунаев'                       -> []  (не адрес — ищем как слово)
    """
    text = str(raw or '').strip()
    if not text:
        return []
    found = extract_all_email_addresses(text)
    cleaned = text.strip(_ADDRESS_EDGE_JUNK)
    if cleaned and cleaned != text:
        for addr in extract_all_email_addresses(cleaned):
            if addr not in found:
                found.append(addr)
    if not found:
        # Адрес, склеенный с мусором внутри токена ('a@b.ru.' / 'Имя a@b.ru').
        m = _EMAIL_IN_TEXT_RE.search(cleaned or text)
        if m:
            found.append(m.group(0).rstrip('.'))
    return found


def _field_tokens(raw):
    """Токены для адресных полей фильтра («От кого», «Кому», «Копия»).

    Адрес в любом оформлении отдаётся bare-адресом (внутри поля токены
    объединяются через ИЛИ), всё остальное остаётся словом как есть.
    """
    tokens = []
    for part in _split_tokens(raw):
        addresses = _token_addresses(part)
        tokens.extend(addresses if addresses else [part])
    return [t for t in tokens if t]


def _query_tokens(raw):
    """Токены общего поиска: пары (значение, это_адрес).

    Слова делятся по пробелам/запятым/точкам с запятой, адрес в любом
    оформлении ('<a@b.ru>', 'Имя <a@b.ru>', 'a@b.ru.') сводится к bare-адресу.
    """
    tokens = []
    for part in re.split(r'[,;\s]+', str(raw or '')):
        part = part.strip()
        if not part:
            continue
        addresses = _token_addresses(part)
        if addresses:
            tokens.extend((addr, True) for addr in addresses)
        else:
            tokens.append((part, False))
    return tokens


# Поля общего поиска («везде»): тема + все адресные поля + наименование.
SEARCH_ANYWHERE_FIELDS = (
    'subject', 'sender', 'sender_name', 'receiver', 'cc', 'bcc', 'name',
)


def _ci_variants(token):
    """Варианты регистра для токена.

    SQLite LIKE (а значит и Django __icontains) регистронезависим только
    для ASCII. Для кириллицы 'совещание' не найдёт 'Совещание' и наоборот.
    Поэтому ищем сразу по нескольким вариантам через ИЛИ.
    """
    t = (token or '').strip()
    if not t:
        return []
    variants = {t, t.lower(), t.upper(), t.capitalize(), t.title()}
    return [v for v in variants if v]


def _q_field_variants(field, token):
    """Q(field__icontains=вариант) объединённые через ИЛИ."""
    q = Q()
    for v in _ci_variants(token):
        q |= Q(**{f'{field}__icontains': v})
    return q


def _q_token_anywhere(token, include_body=False):
    """Один токен общего поиска: любое поле из SEARCH_ANYWHERE_FIELDS (ИЛИ).

    include_body=True — дополнительно ищем в теле письма (body_text),
    т.е. режим «Тема + тело письма».
    """
    q = Q()
    for field in SEARCH_ANYWHERE_FIELDS:
        q |= _q_field_variants(field, token)
    if include_body:
        q |= _q_field_variants('body_text', token)
    return q


def filter_emails(queryset, cleaned_data):
    # Строгий поиск: каждое поле ищет ТОЛЬКО в своём поле письма.
    # Мульти-ввод: токены через запятую объединяются через ИЛИ внутри поля.
    # Разные поля комбинируются через И (цепочка .filter()).
    # Адрес нормализуется до bare-адреса ('<a@b.ru>', 'Имя <a@b.ru>', 'a@b.ru.'
    # → 'a@b.ru'): в письме он хранится без скобок и точек, поэтому запрос,
    # скопированный из письма «как есть», раньше молча ничего не находил.
    if cleaned_data.get('sender'):
        q = Q()
        for t in _field_tokens(cleaned_data['sender']):
            q |= _q_field_variants('sender', t) | _q_field_variants('sender_name', t)
        if q:
            queryset = queryset.filter(q)
    if cleaned_data.get('receiver'):
        q = Q()
        for t in _field_tokens(cleaned_data['receiver']):
            q |= _q_field_variants('receiver', t)
        if q:
            queryset = queryset.filter(q)
    if cleaned_data.get('cc'):
        q = Q()
        for t in _field_tokens(cleaned_data['cc']):
            q |= _q_field_variants('cc', t)
        if q:
            queryset = queryset.filter(q)
    if cleaned_data.get('project_site'):
        queryset = queryset.filter(project_site__in=cleaned_data['project_site'])
    if cleaned_data.get('contractor'):
        queryset = queryset.filter(contractor__in=cleaned_data['contractor'])
    if cleaned_data.get('category'):
        queryset = queryset.filter(category__in=cleaned_data['category'])
    if cleaned_data.get('building_type'):
        queryset = queryset.filter(building_type__in=cleaned_data['building_type'])
    if cleaned_data.get('info'):
        queryset = queryset.filter(info__in=cleaned_data['info'])
    if cleaned_data.get('tags'):
        queryset = queryset.filter(email_tags__tag__in=cleaned_data['tags']).distinct()
    if cleaned_data.get('has_attachments'):
        queryset = queryset.filter(attachments__isnull=False).distinct()
    if cleaned_data.get('is_important'):
        queryset = queryset.filter(is_important=True)
    if cleaned_data.get('is_unread'):
        queryset = queryset.filter(is_read=False)
    if cleaned_data.get('date_from') or cleaned_data.get('date_to'):
        # Дата письма: email_stamp, а для отправленных из приложения
        # (там штамп пуст) — sent_at/creation_stamp, иначе их не найти.
        queryset = queryset.annotate(
            _eff_date=Coalesce(TruncDate('email_stamp'), TruncDate('sent_at'),
                               TruncDate('creation_stamp')),
        )
        if cleaned_data.get('date_from'):
            queryset = queryset.filter(_eff_date__gte=cleaned_data['date_from'])
        if cleaned_data.get('date_to'):
            queryset = queryset.filter(_eff_date__lte=cleaned_data['date_to'])
    if cleaned_data.get('folder'):
        queryset = queryset.filter(folder=cleaned_data['folder'])
    if cleaned_data.get('sent_status'):
        queryset = queryset.filter(sent_status=cleaned_data['sent_status'])
    if cleaned_data.get('search'):
        query = (cleaned_data['search'] or '').strip()
        # Общий поиск — везде (ИЛИ по полям). Слова через пробел/запятую —
        # каждое должно найтись где-то (И): «совещание К-1» найдёт
        # «Совещание 10.09.25 на К-1» независимо от регистра.
        # search_scope: '' (везде без тела) / subject (только тема) /
        # subject_body (везде + тело письма).
        # Адрес (есть '@') ищется по адресным полям при ЛЮБОЙ области: в теме
        # письма адресов не бывает, и «Только тема» молча не находил адресата.
        scope = cleaned_data.get('search_scope') or ''
        include_body = scope == 'subject_body'
        for tok, is_address in _query_tokens(query):
            if scope == 'subject' and not is_address:
                queryset = queryset.filter(_q_field_variants('subject', tok))
            else:
                queryset = queryset.filter(_q_token_anywhere(tok, include_body=include_body))
    return queryset
