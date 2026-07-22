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
