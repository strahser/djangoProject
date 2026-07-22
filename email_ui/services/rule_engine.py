import json
import logging
import re
from typing import Any, Dict, List, Optional

from django.db.models import QuerySet
from django.utils import timezone

from Emails.models import Email
from email_ui.models import EmailRule, EmailAutomationLog, EmailTag, EmailEmailTag

logger = logging.getLogger(__name__)


class RuleEvaluator:
    """
    Evaluates email against rule conditions.
    """

    CONDITIONS = {
        'subject_contains': lambda e, v: v.lower() in (e.subject or '').lower(),
        'subject_equals': lambda e, v: (e.subject or '').lower() == v.lower(),
        'subject_regex': lambda e, v: bool(re.search(v, e.subject or '')),
        'sender_contains': lambda e, v: v.lower() in (e.sender or '').lower(),
        'sender_equals': lambda e, v: (e.sender or '').lower() == v.lower(),
        'sender_domain': lambda e, v: v.lower() in (e.sender or '').lower().split('@')[-1] if '@' in (e.sender or '') else False,
        'receiver_contains': lambda e, v: v.lower() in (e.receiver or '').lower(),
        'has_attachments': lambda e, v: e.attachments.exists() if v else not e.attachments.exists(),
        'is_important': lambda e, v: e.is_important == v,
        'is_read': lambda e, v: e.is_read == v,
        'folder_equals': lambda e, v: e.folder == v,
        'has_tags': lambda e, v: e.email_tags.exists() if v else not e.email_tags.exists(),
        'tag_equals': lambda e, v: e.email_tags.filter(tag__name__iexact=v).exists(),
        'email_type': lambda e, v: e.email_type == v,
        'project_equals': lambda e, v: e.project_site and e.project_site.name.lower() == v.lower(),
        'contractor_equals': lambda e, v: e.contractor and e.contractor.name.lower() == v.lower(),
    }

    @classmethod
    def evaluate(cls, email: Email, conditions: List[Dict[str, Any]]) -> bool:
        """Evaluate all conditions (AND logic)."""
        if not conditions:
            return True

        for condition in conditions:
            field = condition.get('field', '')
            operator = condition.get('operator', 'contains')
            value = condition.get('value', '')

            key = f'{field}_{operator}'
            evaluator = cls.CONDITIONS.get(key)
            if evaluator and not evaluator(email, value):
                return False
            elif evaluator is None:
                logger.warning(f'Unknown condition: {key}')

        return True


class RuleExecutor:
    """
    Executes rule actions on email.
    """

    ACTIONS = {}

    @classmethod
    def register_action(cls, name: str):
        def decorator(func):
            cls.ACTIONS[name] = func
            return func
        return decorator

    @classmethod
    def execute(cls, email: Email, actions: List[Dict[str, Any]]) -> List[str]:
        """Execute all actions, returns list of action descriptions."""
        results = []
        for action_def in actions:
            action = action_def.get('action', '')
            params = action_def.get('params', {})
            executor = cls.ACTIONS.get(action)
            if executor:
                try:
                    result = executor(email, **params)
                    results.append(f'{action}: {result}')
                except Exception as e:
                    logger.exception(f'Action {action} failed: {e}')
                    results.append(f'{action}: error - {e}')
            else:
                logger.warning(f'Unknown action: {action}')
        return results


@RuleExecutor.register_action('add_tag')
def _add_tag(email: Email, tag_id: Optional[int] = None, tag_name: Optional[str] = None):
    if tag_id:
        tag = EmailTag.objects.get(id=tag_id)
    elif tag_name:
        tag, _ = EmailTag.objects.get_or_create(name=tag_name)
    else:
        return 'no tag specified'
    EmailEmailTag.objects.get_or_create(email=email, tag=tag)
    return f'tag "{tag.name}" added'


@RuleExecutor.register_action('remove_tag')
def _remove_tag(email: Email, tag_id: Optional[int] = None, tag_name: Optional[str] = None):
    if tag_id:
        EmailEmailTag.objects.filter(email=email, tag_id=tag_id).delete()
        return f'tag {tag_id} removed'
    elif tag_name:
        EmailEmailTag.objects.filter(email=email, tag__name=tag_name).delete()
        return f'tag "{tag_name}" removed'
    return 'no tag specified'


@RuleExecutor.register_action('move_to_folder')
def _move_to_folder(email: Email, folder: str = 'archive'):
    email.folder = folder
    email.save(update_fields=['folder'])
    return f'moved to "{folder}"'


@RuleExecutor.register_action('mark_read')
def _mark_read(email: Email, **kwargs):
    email.is_read = True
    email.save(update_fields=['is_read'])
    return 'marked as read'


@RuleExecutor.register_action('mark_important')
def _mark_important(email: Email, value: bool = True):
    email.is_important = value
    email.save(update_fields=['is_important'])
    return 'marked as important' if value else 'unmarked as important'


@RuleExecutor.register_action('mark_unread')
def _mark_unread(email: Email, **kwargs):
    email.is_read = False
    email.save(update_fields=['is_read'])
    return 'marked as unread'


class RuleEngine:
    """
    Processes emails through the rules engine.
    """

    def __init__(self):
        self.rules = EmailRule.objects.filter(is_active=True).order_by('-priority')

    def process_email(self, email: Email) -> List[EmailAutomationLog]:
        """Run all active rules against a single email."""
        logs = []

        for rule in self.rules:
            try:
                conditions = rule.conditions if isinstance(rule.conditions, list) else [rule.conditions]
                actions = rule.actions if isinstance(rule.actions, list) else [rule.actions]

                if RuleEvaluator.evaluate(email, conditions):
                    action_results = RuleExecutor.execute(email, actions)
                    action_taken = '; '.join(action_results)

                    log = EmailAutomationLog.objects.create(
                        rule=rule,
                        email=email,
                        success=True,
                        action_taken=action_taken,
                    )
                    logs.append(log)
                    logger.info(f'Rule "{rule.name}" applied to email {email.id}: {action_taken}')
            except Exception as e:
                logger.exception(f'Rule "{rule.name}" failed for email {email.id}: {e}')
                log = EmailAutomationLog.objects.create(
                    rule=rule,
                    email=email,
                    success=False,
                    error_message=str(e),
                )
                logs.append(log)

        return logs

    def process_emails(self, emails: QuerySet) -> int:
        """Run all rules against a queryset of emails."""
        count = 0
        for email in emails:
            self.process_email(email)
            count += 1
        return count

    def run_rules_for_new_email(self, email: Email):
        """Run rules on a single email (for signal handlers)."""
        return self.process_email(email)
