import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional

from django.db.models import QuerySet

from Emails.models import Email

logger = logging.getLogger(__name__)


class ThreadService:
    """
    Builds conversation threads by grouping related emails
    using Message-ID, In-Reply-To, References, and subject.
    """

    SUBJECT_CLEANUP_RE = re.compile(r'^(?:\s*)(?:Re|Fwd|Fw|AW|WG|Antwort|SV|VS)(?:\s*:?\s*)', re.IGNORECASE)

    @classmethod
    def normalize_subject(cls, subject: str) -> str:
        """Strip reply/forward prefixes from subject."""
        if not subject:
            return ''
        cleaned = subject.strip()
        while cls.SUBJECT_CLEANUP_RE.match(cleaned):
            cleaned = cls.SUBJECT_CLEANUP_RE.sub('', cleaned).strip()
        return cleaned.lower()

    @classmethod
    def get_thread_id(cls, email: Email) -> Optional[str]:
        """
        Determine thread_id from email fields.
        Uses References header first, then In-Reply-To, then subject hash.
        """
        if email.references:
            refs = [r.strip() for r in email.references.split() if r.strip()]
            if refs:
                return refs[0]
        if email.in_reply_to:
            return email.in_reply_to.strip()
        if email.message_id:
            return email.message_id.strip()
        return None

    @classmethod
    def build_threads(cls, emails: QuerySet) -> Dict[str, List[Email]]:
        """Group emails into threads."""
        threads = defaultdict(list)

        for email in emails:
            thread_id = email.thread_id or cls.get_thread_id(email)
            if thread_id:
                threads[thread_id].append(email)
            else:
                # Group by normalized subject
                norm_subj = cls.normalize_subject(email.subject)
                if norm_subj:
                    threads[f'subject:{norm_subj}'].append(email)
                else:
                    threads[f'orphan:{email.id}'] = [email]

        # Sort each thread by date
        for tid in threads:
            threads[tid].sort(key=lambda e: e.email_stamp or e.creation_stamp or e.id)

        return dict(threads)

    @classmethod
    def get_thread(cls, email: Email) -> List[Email]:
        """Get the full conversation thread for an email."""
        thread_id = email.thread_id or cls.get_thread_id(email)
        if not thread_id:
            return [email]

        base_qs = Email.objects.all()

        # Find by exact thread_id
        thread_emails = list(base_qs.filter(thread_id=thread_id).order_by('email_stamp', 'creation_stamp'))
        if thread_emails:
            return thread_emails

        # Find by message_id chain
        msg_id = email.message_id
        if not msg_id:
            return [email]

        # Walk in_reply_to chain
        result = {email.id: email}
        current = email

        # Walk backwards (find earlier emails in the thread)
        while current.in_reply_to:
            prev = base_qs.filter(message_id=current.in_reply_to.strip()).first()
            if not prev:
                break
            result[prev.id] = prev
            current = prev

        # Walk forwards (find later replies)
        replies = base_qs.filter(in_reply_to=msg_id).order_by('email_stamp', 'creation_stamp')
        for reply in replies:
            result[reply.id] = reply

        return sorted(result.values(), key=lambda e: e.email_stamp or e.creation_stamp or e.id)

    @classmethod
    def auto_thread(cls, email: Email) -> Optional[str]:
        """Auto-assign thread_id to email based on headers."""
        thread_id = cls.get_thread_id(email)
        if thread_id:
            email.thread_id = thread_id
            email.save(update_fields=['thread_id'])
            return thread_id

        # Try to find sibling by normalized subject
        norm_subj = cls.normalize_subject(email.subject)
        if norm_subj:
            sibling = Email.objects.filter(subject__icontains=norm_subj).exclude(id=email.id).first()
            if sibling and sibling.thread_id:
                email.thread_id = sibling.thread_id
                email.save(update_fields=['thread_id'])
                return sibling.thread_id

        return None


# --- Блок 28 (B2): обёртки цепочек для views (переезд 1:1) ---

def attach_thread_context(emails, head_cache=None, with_head=True):
    """Досчитывает поля для режима цепочек: direction in/out, body_head.

    Мутирует объекты (атрибуты, не колонки БД). head_cache — dict на запрос,
    чтобы не читать один HTML-файл дважды. with_head=False — только direction
    (дешёво, без чтения файлов: для подсчёта Вх./Исх. до пагинации).
    """
    from email_ui.utils import email_body_head
    if head_cache is None:
        head_cache = {}
    for email in emails:
        email.direction = (
            'out' if (email.email_type or '').upper() == 'OUT' else 'in'
        )
        email.direction_label = 'Исходящее' if email.direction == 'out' else 'Входящее'
        if with_head and not getattr(email, 'body_head', ''):
            try:
                email.body_head = email_body_head(email, 220, head_cache)
            except Exception:
                email.body_head = ''
        elif not hasattr(email, 'body_head'):
            email.body_head = ''


def build_thread_list(emails):
    """Группирует письма в цепочки по теме (ThreadService), сортирует по свежим.

    Возвращает список dict: key/subject/emails/count/in_count/out_count/earliest/latest.
    Письма внутри — хронологически (старые сверху, как чтение переписки).
    """
    threads = ThreadService.build_threads(emails)
    out = []
    for key, msgs in threads.items():
        # Только direction (без чтения файлов) — головы дочитаем после пагинации.
        attach_thread_context(msgs, with_head=False)
        latest = max(
            (m.email_stamp or m.creation_stamp for m in msgs if m.email_stamp or m.creation_stamp),
            default=None,
        )
        earliest = min(
            (m.email_stamp or m.creation_stamp for m in msgs if m.email_stamp or m.creation_stamp),
            default=None,
        )
        # Тема для заголовка — из самого свежего письма (сохраняет Re:/Fwd:).
        subj_src = max(msgs, key=lambda m: (m.email_stamp or m.creation_stamp or m.id))
        out.append({
            'key': key,
            'subject': (subj_src.subject or '').strip() or 'Без темы',
            'emails': msgs,
            'count': len(msgs),
            'in_count': sum(1 for m in msgs if m.direction == 'in'),
            'out_count': sum(1 for m in msgs if m.direction == 'out'),
            'earliest': earliest,
            'latest': latest,
        })
    def _thread_ts(t):
        dt = t['latest']
        try:
            return dt.timestamp() if dt else float('-inf')
        except Exception:
            return float('-inf')
    out.sort(key=_thread_ts, reverse=True)
    return out


def attach_thread_page_heads(thread_page):
    """Дочитывает body_head только для писем текущей страницы цепочек."""
    head_cache = {}
    for t in thread_page:
        attach_thread_context(t['emails'], head_cache, with_head=True)


def build_selection_threads(selected_ids):
    """Цепочки для выбранных писем: сами письма + связанные из inbox+sent.

    Связь — общий thread_id или одинаковая нормализованная тема
    (ThreadService.normalize_subject: режутся Re:/Fwd: и т.п.).
    Выбранные включаются всегда, даже из других папок.
    """
    sel = list(Email.objects.filter(pk__in=selected_ids))
    if not sel:
        return []
    norms, tids = set(), set()
    for e in sel:
        n = ThreadService.normalize_subject(e.subject or '')
        if n:
            norms.add(n)
        tid = (e.thread_id or '').strip()
        if tid:
            tids.add(tid)
    matched = {e.pk for e in sel}
    if norms or tids:
        rows = Email.objects.filter(folder__in=('inbox', 'sent')).values(
            'id', 'subject', 'thread_id')
        for r in rows:
            rtid = (r['thread_id'] or '').strip()
            if rtid and rtid in tids:
                matched.add(r['id'])
                continue
            if norms and ThreadService.normalize_subject(r['subject'] or '') in norms:
                matched.add(r['id'])
    emails = list(
        Email.objects.filter(pk__in=matched).select_related(
            'project_site', 'contractor', 'category', 'building_type',
        ).prefetch_related('attachments'))
    thread_list = build_thread_list(emails)
    attach_thread_page_heads(thread_list)
    return thread_list
