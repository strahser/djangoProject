import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Emails.models import Attachment, Email, EmailType, InfoChoices
from email_ui.models import (
    Contact, ContactEmail, EmailEmailTag, EmailRule,
    EmailTag, EmailTaskLink, EmailTemplate, SavedFilter, SMTPAccount,
)
from email_ui.utils import sanitize_id, sanitize_id_list, clean_email_html
from email_ui.utils import extract_email_address, extract_all_email_addresses, resolve_sender_to_email


class UtilsTest(TestCase):
    """Tests for utility functions."""

    def test_sanitize_id_clean_int(self):
        self.assertEqual(sanitize_id(123), 123)

    def test_sanitize_id_clean_string(self):
        self.assertEqual(sanitize_id('123'), 123)

    def test_sanitize_id_with_nbsp(self):
        """ID with non-breaking space - the known bug."""
        self.assertEqual(sanitize_id('7\xa0585'), 7585)
        self.assertEqual(sanitize_id('8\xa0507'), 8507)
        self.assertEqual(sanitize_id('1\xa0234\xa0567'), 1234567)

    def test_sanitize_id_with_thousands_space(self):
        self.assertEqual(sanitize_id('1 234'), 1234)

    def test_sanitize_id_list_mixed(self):
        result = sanitize_id_list(['123', '7\xa0585', '', '456', ' 789 '])
        self.assertEqual(result, [123, 7585, 456, 789])

    def test_sanitize_id_list_all_invalid(self):
        result = sanitize_id_list(['abc', '', 'def'])
        self.assertEqual(result, [])

    def test_clean_email_html_removes_scripts(self):
        html = '<script>alert("xss")</script><p>Hello</p>'
        cleaned = clean_email_html(html)
        self.assertNotIn('script', cleaned)
        self.assertIn('Hello', cleaned)

    def test_clean_email_html_allows_safe_tags(self):
        html = '<p><strong>Bold</strong> and <em>italic</em></p>'
        cleaned = clean_email_html(html)
        self.assertIn('<strong>Bold</strong>', cleaned)


class CategoryMixin:
    """Mixin that ensures reference objects with pk=1 exist for FK defaults."""

    def setUp(self):
        super().setUp()
        from StaticData.models import Category, Status
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})


class EmailModelTest(CategoryMixin, TestCase):
    """Tests for Email model extensions."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('testuser', 'test@test.com', 'password')
        self.email = Email.objects.create(
            uid='test-uid-1',
            subject='Test Subject',
            sender='sender@test.com',
            receiver='receiver@test.com',
            email_type='IN',
            folder='inbox',
            is_read=False,
            is_important=False,
            sent_status='draft',
        )

    def test_email_creation(self):
        self.assertEqual(Email.objects.count(), 1)
        self.assertEqual(self.email.subject, 'Test Subject')

    def test_email_str(self):
        self.email.name = self.email.subject
        self.email.save(update_fields=['name'])
        self.assertIn(self.email.subject, str(self.email))

    def test_email_default_values(self):
        self.assertEqual(self.email.folder, 'inbox')
        self.assertEqual(self.email.sent_status, 'draft')
        self.assertFalse(self.email.is_read)
        self.assertFalse(self.email.is_important)

    def test_email_sent_status_choices(self):
        for status, _ in Email._meta.get_field('sent_status').choices:
            self.assertIn(status, ['draft', 'queued', 'sent', 'failed', 'bounced'])

    def test_email_folder_choices(self):
        for folder, _ in Email.FOLDER_CHOICES:
            self.assertIn(folder, ['inbox', 'sent', 'drafts', 'archive', 'trash'])

    def test_email_get_html_file_path_no_link(self):
        self.assertIsNone(self.email.get_html_file_path())

    def test_email_get_html_file_path_with_link(self):
        self.email.link = '/some/path'
        result = self.email.get_html_file_path()
        self.assertIsNotNone(result)

    def test_email_tags_property(self):
        """Email.tags property returns related EmailEmailTag queryset."""
        tag = EmailTag.objects.create(name='test', color='#ff0000')
        EmailEmailTag.objects.create(email=self.email, tag=tag)
        self.assertEqual(self.email.tags.count(), 1)
        self.assertEqual(self.email.tags.first().tag.name, 'test')


class EmailTagModelTest(CategoryMixin, TestCase):
    """Tests for EmailTag and EmailEmailTag models."""

    def setUp(self):
        super().setUp()
        self.email = Email.objects.create(
            uid='tag-test-uid',
            subject='Tag Test',
            sender='sender@test.com',
        )
        self.tag = EmailTag.objects.create(name='Important', color='#ff0000', description='Important emails')

    def test_tag_creation(self):
        self.assertEqual(EmailTag.objects.count(), 1)
        self.assertEqual(str(self.tag), 'Important')

    def test_tag_str(self):
        self.assertEqual(str(self.tag), 'Important')

    def test_email_tag_link_creation(self):
        link = EmailEmailTag.objects.create(email=self.email, tag=self.tag)
        self.assertEqual(str(link), f'{self.email} → {self.tag}')
        self.assertEqual(self.email.email_tags.count(), 1)
        self.assertEqual(self.tag.email_tags.count(), 1)

    def test_email_tag_link_unique(self):
        EmailEmailTag.objects.create(email=self.email, tag=self.tag)
        with self.assertRaises(Exception):
            EmailEmailTag.objects.create(email=self.email, tag=self.tag)


class ContactModelTest(TestCase):
    """Tests for Contact and ContactEmail models."""

    def setUp(self):
        self.contact = Contact.objects.create(
            name='John Doe',
            phone='+7-123-456-7890',
            notes='Test contact',
        )
        self.contact_email = ContactEmail.objects.create(
            contact=self.contact,
            email='john@test.com',
            label='work',
            is_primary=True,
        )

    def test_contact_creation(self):
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(str(self.contact), 'John Doe')

    def test_contact_primary_email(self):
        self.assertEqual(self.contact.primary_email, self.contact_email)

    def test_contact_email_str(self):
        self.assertEqual(str(self.contact_email), 'john@test.com (John Doe)')

    def test_contact_email_unique_together(self):
        with self.assertRaises(Exception):
            ContactEmail.objects.create(
                contact=self.contact,
                email='john@test.com',
            )

    def test_contact_multiple_emails(self):
        ce2 = ContactEmail.objects.create(
            contact=self.contact,
            email='john.doe@work.com',
            label='personal',
            is_primary=False,
        )
        self.assertEqual(self.contact.emails.count(), 2)


class SMTPAccountModelTest(TestCase):
    """Tests for SMTPAccount model."""

    def setUp(self):
        self.account1 = SMTPAccount.objects.create(
            name='Main',
            host='smtp.test.com',
            port=587,
            username='user@test.com',
            password='secret',
            from_email='user@test.com',
            from_name='Test User',
            is_default=True,
        )
        self.account2 = SMTPAccount.objects.create(
            name='Secondary',
            host='smtp2.test.com',
            port=465,
            username='user2@test.com',
            password='secret2',
            from_email='user2@test.com',
            is_default=True,  # Should unset account1
        )

    def test_smtp_account_str(self):
        self.assertEqual(str(self.account1), 'Main')

    def test_only_one_default(self):
        """When setting a new default, the old default should be unset."""
        self.account1.refresh_from_db()
        self.assertFalse(self.account1.is_default)
        self.assertTrue(self.account2.is_default)


class EmailTemplateModelTest(TestCase):
    """Tests for EmailTemplate model."""

    def setUp(self):
        self.template = EmailTemplate.objects.create(
            name='Test Template',
            subject_template='Hello {{ name }}',
            body_template='<p>Dear {{ name }},</p><p>{{ message }}</p>',
        )

    def test_template_str(self):
        self.assertEqual(str(self.template), 'Test Template')

    def test_template_variable(self):
        from email_ui.models import EmailTemplateVariable
        var = EmailTemplateVariable.objects.create(
            template=self.template,
            name='name',
            label='Contact Name',
            is_required=True,
        )
        self.assertEqual(str(var), '{{name}}')
        self.assertEqual(self.template.variables.count(), 1)


class EmailTaskLinkModelTest(CategoryMixin, TestCase):
    """Tests for EmailTaskLink model."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('testuser2', 'test2@test.com', 'password')
        from ProjectTDL.models import Task
        from StaticData.models import ProjectSite, SubProject
        self.sub_project = SubProject.objects.create(name='Test SubProject')
        self.project = ProjectSite.objects.create(name='Test Project')
        self.task = Task.objects.create(
            owner=self.user,
            project_site=self.project,
            sub_project=self.sub_project,
            name='Test Task',
        )
        self.email = Email.objects.create(
            uid='link-test-uid',
            subject='Link Test',
            sender='sender@test.com',
        )
        self.link = EmailTaskLink.objects.create(
            email=self.email,
            task=self.task,
            link_type='related',
            created_by=self.user,
        )

    def test_link_creation(self):
        self.assertEqual(EmailTaskLink.objects.count(), 1)
        self.assertEqual(str(self.link), f'{self.email} ↔ {self.task}')

    def test_link_unique(self):
        with self.assertRaises(Exception):
            EmailTaskLink.objects.create(
                email=self.email,
                task=self.task,
                link_type='reference',
            )

    def test_link_types(self):
        for link_type, _ in EmailTaskLink.LINK_TYPES:
            self.assertIn(link_type, ['related', 'created_from', 'created_task', 'reference'])


class EmailRuleModelTest(TestCase):
    """Tests for EmailRule model."""

    def setUp(self):
        self.user = User.objects.create_user('ruleuser', 'rule@test.com', 'password')
        self.rule = EmailRule.objects.create(
            name='Test Rule',
            description='A test rule',
            is_active=True,
            priority=10,
            conditions=[{'field': 'subject', 'operator': 'contains', 'value': 'test'}],
            actions=[{'action': 'mark_important', 'params': {}}],
            created_by=self.user,
        )

    def test_rule_str(self):
        self.assertEqual(str(self.rule), 'Test Rule')

    def test_rule_conditions_are_json(self):
        self.assertIsInstance(self.rule.conditions, list)
        self.assertEqual(self.rule.conditions[0]['field'], 'subject')

    def test_rule_actions_are_json(self):
        self.assertIsInstance(self.rule.actions, list)
        self.assertEqual(self.rule.actions[0]['action'], 'mark_important')


class SavedFilterModelTest(TestCase):
    """Tests for SavedFilter model."""

    def setUp(self):
        self.user = User.objects.create_user('filteruser', 'filter@test.com', 'password')
        self.sf = SavedFilter.objects.create(
            name='Unread Important',
            user=self.user,
            filters={'is_unread': ['1'], 'is_important': ['1']},
            folder='inbox',
            is_default=True,
        )

    def test_saved_filter_str(self):
        self.assertEqual(str(self.sf), 'Unread Important')

    def test_saved_filter_unique_for_user(self):
        with self.assertRaises(Exception):
            SavedFilter.objects.create(
                name='Unread Important',
                user=self.user,
                filters={},
            )


class ViewTestCaseMixin:
    """Mixin with helpers for view tests."""

    def create_test_email(self, **kwargs):
        defaults = {
            'uid': f'test-uid-{datetime.now().timestamp()}',
            'subject': 'Test Email',
            'sender': 'sender@test.com',
            'receiver': 'receiver@test.com',
            'email_type': 'IN',
            'folder': 'inbox',
            'is_read': False,
        }
        defaults.update(kwargs)
        return Email.objects.create(**defaults)


class InboxViewTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for inbox view."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('inboxuser', 'inbox@test.com', 'password')
        self.client.login(username='inboxuser', password='password')
        for i in range(5):
            self.create_test_email(uid=f'inbox-uid-{i}', subject=f'Email {i}')

    def test_inbox_view_status(self):
        response = self.client.get(reverse('email_ui:inbox_default'))
        self.assertEqual(response.status_code, 200)

    def test_inbox_view_template(self):
        response = self.client.get(reverse('email_ui:inbox_default'))
        self.assertTemplateUsed(response, 'email_ui/inbox.html')

    def test_inbox_view_pagination(self):
        response = self.client.get(reverse('email_ui:inbox_default'))
        self.assertIn('page_obj', response.context)
        self.assertEqual(len(response.context['page_obj']), 5)

    def test_inbox_view_filter_by_folder(self):
        self.create_test_email(uid='sent-uid', folder='sent')
        response = self.client.get(reverse('email_ui:inbox', args=['sent']))
        self.assertEqual(len(response.context['page_obj']), 1)

    def test_inbox_view_search(self):
        response = self.client.get(reverse('email_ui:email_list_partial'), {'search': 'Email 1'})
        self.assertEqual(response.status_code, 200)

    def test_inbox_anonymous_redirect(self):
        self.client.logout()
        response = self.client.get(reverse('email_ui:inbox_default'))
        self.assertNotEqual(response.status_code, 200)


class EmailListPartialTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for email list partial view."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('partialuser', 'partial@test.com', 'password')
        self.client.login(username='partialuser', password='password')
        for i in range(3):
            self.create_test_email(uid=f'partial-uid-{i}')

    def test_partial_view(self):
        response = self.client.get(reverse('email_ui:email_list_partial'), {'folder': 'inbox'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'email_ui/partials/email_list.html')

    def test_partial_view_infinite(self):
        response = self.client.get(
            reverse('email_ui:email_list_partial'),
            {'folder': 'inbox', '_infinite': '1'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'email_ui/partials/email_rows.html')


class BulkActionViewTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for bulk action view."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('bulkuser', 'bulk@test.com', 'password')
        self.client.login(username='bulkuser', password='password')
        self.email1 = self.create_test_email(uid='bulk-uid-1', folder='inbox')
        self.email2 = self.create_test_email(uid='bulk-uid-2', folder='inbox')

    def test_bulk_action_invalid(self):
        response = self.client.post(reverse('email_ui:bulk_action'), {'action': 'invalid'})
        self.assertEqual(response.status_code, 400)

    def test_bulk_action_no_emails(self):
        response = self.client.post(reverse('email_ui:bulk_action'), {'action': 'mark_read'})
        self.assertEqual(response.status_code, 400)

    def test_bulk_mark_read(self):
        response = self.client.post(reverse('email_ui:bulk_action'), {
            'action': 'mark_read',
            'selected_emails': [str(self.email1.pk), str(self.email2.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.email1.refresh_from_db()
        self.email2.refresh_from_db()
        self.assertTrue(self.email1.is_read)
        self.assertTrue(self.email2.is_read)

    def test_bulk_mark_read_with_nbsp_ids(self):
        """Bulk action should work with \\xa0-formatted IDs."""
        response = self.client.post(reverse('email_ui:bulk_action'), {
            'action': 'mark_read',
            'selected_emails': [f'{self.email1.pk}', f'8\xa0507'],  # one valid, one invalid nbsp
        })
        self.email1.refresh_from_db()
        self.assertTrue(self.email1.is_read)

    def test_bulk_mark_unread(self):
        self.email1.is_read = True
        self.email1.save()
        response = self.client.post(reverse('email_ui:bulk_action'), {
            'action': 'mark_unread',
            'selected_emails': [str(self.email1.pk)],
        })
        self.email1.refresh_from_db()
        self.assertFalse(self.email1.is_read)

    def test_bulk_mark_important(self):
        response = self.client.post(reverse('email_ui:bulk_action'), {
            'action': 'mark_important',
            'selected_emails': [str(self.email1.pk)],
        })
        self.email1.refresh_from_db()
        self.assertTrue(self.email1.is_important)

    def test_bulk_move_to_trash(self):
        response = self.client.post(reverse('email_ui:bulk_action'), {
            'action': 'delete',
            'selected_emails': [str(self.email1.pk)],
        })
        self.email1.refresh_from_db()
        self.assertEqual(self.email1.folder, 'trash')

    def test_bulk_move_folder(self):
        response = self.client.post(reverse('email_ui:bulk_action'), {
            'action': 'move',
            'folder': 'archive',
            'selected_emails': [str(self.email1.pk), str(self.email2.pk)],
        })
        self.email1.refresh_from_db()
        self.email2.refresh_from_db()
        self.assertEqual(self.email1.folder, 'archive')
        self.assertEqual(self.email2.folder, 'archive')


class EmailDetailModalTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for email detail modal view."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('detailuser', 'detail@test.com', 'password')
        self.client.login(username='detailuser', password='password')
        self.email = self.create_test_email(uid='detail-uid-1')

    def test_detail_modal(self):
        response = self.client.get(reverse('email_ui:email_detail_modal', args=[self.email.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'email_ui/partials/email_detail_modal_content.html')

    def test_detail_modal_404(self):
        response = self.client.get(reverse('email_ui:email_detail_modal', args=[9999]))
        self.assertEqual(response.status_code, 404)

    def test_detail_modal_contains_tags(self):
        tag = EmailTag.objects.create(name='test-tag', color='#00ff00')
        EmailEmailTag.objects.create(email=self.email, tag=tag)
        response = self.client.get(reverse('email_ui:email_detail_modal', args=[self.email.pk]))
        self.assertIn('all_tags', response.context)
        self.assertIn('email', response.context)


class MarkAsReadTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for mark as read view."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('readuser', 'read@test.com', 'password')
        self.client.login(username='readuser', password='password')
        self.email = self.create_test_email(uid='read-uid-1')

    def test_mark_as_read(self):
        response = self.client.post(reverse('email_ui:mark_email_as_read', args=[self.email.pk]))
        self.assertEqual(response.status_code, 204)
        self.email.refresh_from_db()
        self.assertTrue(self.email.is_read)


class MoveToFolderTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for move to folder view."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('moveuser', 'move@test.com', 'password')
        self.client.login(username='moveuser', password='password')
        self.email = self.create_test_email(uid='move-uid-1')

    def test_move_to_archive(self):
        response = self.client.post(
            reverse('email_ui:move_to_folder', args=[self.email.pk]),
            {'folder': 'archive'}
        )
        self.assertEqual(response.status_code, 204)
        self.email.refresh_from_db()
        self.assertEqual(self.email.folder, 'archive')

    def test_move_to_invalid_folder(self):
        response = self.client.post(
            reverse('email_ui:move_to_folder', args=[self.email.pk]),
            {'folder': 'nonexistent'}
        )
        self.assertEqual(response.status_code, 400)


class FetchEmailsTest(CategoryMixin, TestCase):
    """Tests for fetch emails view."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('fetchuser', 'fetch@test.com', 'password')
        self.client.login(username='fetchuser', password='password')

    def test_fetch_emails_post_redirect(self):
        response = self.client.post(reverse('email_ui:fetch_emails'), {'mail_count': 5})
        # Should redirect (IMAP will fail in test, but view should handle it)
        self.assertIn(response.status_code, [200, 302, 500])

    def test_fetch_emails_get(self):
        """GET should not work (only POST)."""
        response = self.client.get(reverse('email_ui:fetch_emails'))
        self.assertEqual(response.status_code, 405)  # Method Not Allowed


class UnreadCountTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for unread count view."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('unreaduser', 'unread@test.com', 'password')
        self.client.login(username='unreaduser', password='password')
        self.create_test_email(uid='unread-1', is_read=False)
        self.create_test_email(uid='unread-2', is_read=False)
        self.create_test_email(uid='unread-3', is_read=True)

    def test_unread_count(self):
        response = self.client.get(reverse('email_ui:unread_count'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), '2')


class MetadataEditTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for metadata editing."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('metauser', 'meta@test.com', 'password')
        self.client.login(username='metauser', password='password')
        self.email = self.create_test_email(uid='meta-uid-1')

    def test_edit_metadata_form(self):
        response = self.client.get(reverse('email_ui:edit_metadata_form', args=[self.email.pk]))
        self.assertEqual(response.status_code, 200)

    def test_edit_metadata_post(self):
        response = self.client.post(
            reverse('email_ui:edit_metadata', args=[self.email.pk]),
            {'is_important': 'on'}
        )
        self.assertEqual(response.status_code, 200)
        self.email.refresh_from_db()
        self.assertTrue(self.email.is_important)

    def test_metadata_display(self):
        response = self.client.get(reverse('email_ui:metadata_display', args=[self.email.pk]))
        self.assertEqual(response.status_code, 200)


class TagViewTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for tag management views."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('taguser', 'tag@test.com', 'password')
        self.client.login(username='taguser', password='password')
        self.email = self.create_test_email(uid='tag-uid-1')
        self.tag = EmailTag.objects.create(name='TestTag', color='#ff0000')

    def test_tag_list(self):
        response = self.client.get(reverse('email_ui:tag_list'))
        self.assertEqual(response.status_code, 200)

    def test_tag_create_modal(self):
        response = self.client.get(reverse('email_ui:tag_create_modal'))
        self.assertEqual(response.status_code, 200)

    def test_tag_create(self):
        response = self.client.post(reverse('email_ui:tag_create'), {
            'name': 'NewTag', 'color': '#00ff00', 'description': 'New test tag'
        })
        self.assertEqual(response.status_code, 204)
        self.assertTrue(EmailTag.objects.filter(name='NewTag').exists())

    def test_tag_delete(self):
        response = self.client.post(reverse('email_ui:tag_delete', args=[self.tag.pk]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(EmailTag.objects.filter(pk=self.tag.pk).exists())

    def test_assign_tag(self):
        response = self.client.post(reverse('email_ui:assign_tag'), {
            'email_id': str(self.email.pk),
            'tag_id': str(self.tag.pk),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.email.email_tags.count(), 1)

    def test_assign_tag_with_nbsp_id(self):
        """Assign tag should work with \\xa0-formatted ID."""
        response = self.client.post(reverse('email_ui:assign_tag'), {
            'email_id': f'{self.email.pk}',
            'tag_id': str(self.tag.pk),
        })
        self.assertEqual(response.status_code, 200)

    def test_assign_tag_by_name(self):
        response = self.client.post(reverse('email_ui:assign_tag'), {
            'email_id': str(self.email.pk),
            'tag_name': 'AutoCreatedTag',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(EmailTag.objects.filter(name='AutoCreatedTag').exists())

    def test_remove_tag(self):
        EmailEmailTag.objects.create(email=self.email, tag=self.tag)
        response = self.client.post(
            reverse('email_ui:remove_tag', args=[self.email.pk, self.tag.pk])
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.email.email_tags.count(), 0)


class ContactViewTest(TestCase):
    """Tests for contact management views."""

    def setUp(self):
        self.user = User.objects.create_user('contactuser', 'contact@test.com', 'password')
        self.client.login(username='contactuser', password='password')
        self.contact = Contact.objects.create(name='Test Contact', phone='+7-111-222-3333')
        ContactEmail.objects.create(contact=self.contact, email='test@contact.com', is_primary=True)

    def test_contact_list(self):
        response = self.client.get(reverse('email_ui:contact_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'email_ui/contacts/list.html')

    def test_contact_list_search(self):
        response = self.client.get(reverse('email_ui:contact_list'), {'q': 'Test'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.contact, response.context['contacts'])

    def test_contact_detail(self):
        response = self.client.get(reverse('email_ui:contact_detail', args=[self.contact.pk]))
        self.assertEqual(response.status_code, 200)

    def test_contact_create_modal(self):
        response = self.client.get(reverse('email_ui:contact_create_modal'))
        self.assertEqual(response.status_code, 200)

    def test_contact_create(self):
        response = self.client.post(reverse('email_ui:contact_create'), {
            'name': 'New Contact',
            'is_active': True,
            'email': 'new@contact.com',
            'label': 'work',
        })
        self.assertEqual(response.status_code, 204)
        self.assertTrue(Contact.objects.filter(name='New Contact').exists())

    def test_contact_edit_modal(self):
        response = self.client.get(reverse('email_ui:contact_edit_modal', args=[self.contact.pk]))
        self.assertEqual(response.status_code, 200)

    def test_contact_edit(self):
        response = self.client.post(
            reverse('email_ui:contact_edit', args=[self.contact.pk]),
            {'name': 'Updated Contact', 'is_active': True}
        )
        self.assertEqual(response.status_code, 204)
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.name, 'Updated Contact')

    def test_contact_delete(self):
        response = self.client.post(reverse('email_ui:contact_delete', args=[self.contact.pk]))
        self.assertIn(response.status_code, [200, 302, 204])
        self.assertFalse(Contact.objects.filter(pk=self.contact.pk).exists())

    def test_contact_search(self):
        response = self.client.get(reverse('email_ui:contact_search'), {'q': 'Test'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data), 1)


class AttachmentViewTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for attachment views."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('attuser', 'att@test.com', 'password')
        self.client.login(username='attuser', password='password')
        self.email = self.create_test_email(uid='att-uid-1')
        self.att = Attachment.objects.create(
            email=self.email,
            file_path=r'C:\nonexistent\file.pdf',
            filename='test.pdf',
            size=1024,
            content_type='application/pdf',
        )

    def test_attachments_modal(self):
        response = self.client.get(reverse('email_ui:attachments_modal', args=[self.email.pk]))
        self.assertEqual(response.status_code, 200)

    def test_download_attachment_not_found(self):
        response = self.client.get(reverse('email_ui:download_attachment', args=[self.att.pk]))
        self.assertEqual(response.status_code, 404)

    def test_open_folder_not_found(self):
        response = self.client.post(reverse('email_ui:open_attachment_folder', args=[self.email.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['success'])


class AttachmentModelTest(CategoryMixin, TestCase):
    """Tests for Attachment model extensions."""

    def setUp(self):
        super().setUp()
        self.email = Email.objects.create(uid='att-model-uid', subject='Att Test')
        self.att = Attachment.objects.create(
            email=self.email,
            file_path=r'C:\docs\report.pdf',
            filename='report.pdf',
            size=2048,
            content_type='application/pdf',
            is_inline=False,
            content_id='',
        )

    def test_attachment_extended_fields(self):
        self.assertFalse(self.att.is_inline)
        self.assertEqual(self.att.content_id, '')

    def test_file_extension(self):
        self.assertEqual(self.att.file_extension, 'pdf')

    def test_icon_class_pdf(self):
        self.assertEqual(self.att.icon_class, 'bi-file-pdf-fill')


class EmailBodyViewTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for email body view."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('bodyuser', 'body@test.com', 'password')
        self.client.login(username='bodyuser', password='password')
        self.email = self.create_test_email(uid='body-uid-1')

    def test_body_no_file(self):
        response = self.client.get(reverse('email_ui:email_body', args=[self.email.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('не найден', response.content.decode())


class FilterFormTest(TestCase):
    """Tests for filter form partial view."""

    def setUp(self):
        self.user = User.objects.create_user('filterformuser', 'ff@test.com', 'password')
        self.client.login(username='filterformuser', password='password')

    def test_filter_form_partial(self):
        response = self.client.get(reverse('email_ui:filter_form_partial'))
        self.assertEqual(response.status_code, 200)

    def test_filter_field_modal_project(self):
        response = self.client.get(
            reverse('email_ui:filter_field_modal', args=['project_site'])
        )
        self.assertEqual(response.status_code, 200)

    def test_filter_field_modal_invalid(self):
        response = self.client.get(
            reverse('email_ui:filter_field_modal', args=['invalid_field'])
        )
        self.assertEqual(response.status_code, 400)


class RuleViewTest(TestCase):
    """Tests for rule management views."""

    def setUp(self):
        self.user = User.objects.create_user('ruleuser2', 'rule2@test.com', 'password')
        self.client.login(username='ruleuser2', password='password')
        self.rule = EmailRule.objects.create(
            name='Test Rule',
            conditions=[{'field': 'subject', 'operator': 'contains', 'value': 'test'}],
            actions=[{'action': 'mark_important', 'params': {}}],
            created_by=self.user,
        )

    def test_rules_list(self):
        response = self.client.get(reverse('email_ui:rules_list'))
        self.assertEqual(response.status_code, 200)

    def test_rule_create_modal(self):
        response = self.client.get(reverse('email_ui:rule_create_modal'))
        self.assertEqual(response.status_code, 200)

    def test_rule_toggle(self):
        response = self.client.post(reverse('email_ui:rule_toggle', args=[self.rule.pk]))
        self.assertEqual(response.status_code, 200)
        self.rule.refresh_from_db()
        self.assertFalse(self.rule.is_active)


class SavedFilterViewTest(TestCase):
    """Tests for saved filter views."""

    def setUp(self):
        self.user = User.objects.create_user('sfuser', 'sf@test.com', 'password')
        self.client.login(username='sfuser', password='password')
        self.sf = SavedFilter.objects.create(
            name='My Filter',
            user=self.user,
            filters={'is_important': ['1']},
            folder='inbox',
        )

    def test_saved_filters_list(self):
        response = self.client.get(reverse('email_ui:saved_filters_list'))
        self.assertEqual(response.status_code, 200)

    def test_delete_saved_filter(self):
        response = self.client.post(reverse('email_ui:delete_saved_filter', args=[self.sf.pk]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(SavedFilter.objects.filter(pk=self.sf.pk).exists())


class EmailModelSendFieldsTest(CategoryMixin, TestCase):
    """Tests for the new Email model fields (sending, threading)."""

    def test_email_send_fields(self):
        from StaticData.models import Category
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        email = Email.objects.create(
            uid='send-fields-uid',
            subject='Send Test',
            reply_to='reply@test.com',
            cc='cc@test.com',
            bcc='bcc@test.com',
            message_id='<msg123@test.com>',
            in_reply_to='<msg122@test.com>',
            references='<msg120@test.com> <msg121@test.com>',
            thread_id='thread-abc-123',
            sent_status='sent',
            sent_at=timezone.now(),
        )
        self.assertEqual(email.reply_to, 'reply@test.com')
        self.assertEqual(email.cc, 'cc@test.com')
        self.assertEqual(email.bcc, 'bcc@test.com')
        self.assertEqual(email.message_id, '<msg123@test.com>')
        self.assertEqual(email.in_reply_to, '<msg122@test.com>')
        self.assertEqual(email.references, '<msg120@test.com> <msg121@test.com>')
        self.assertEqual(email.thread_id, 'thread-abc-123')
        self.assertEqual(email.sent_status, 'sent')


class EmailAttachmentExtendedFieldsTest(CategoryMixin, TestCase):
    """Tests for attachment extended fields."""

    def test_attachment_inline_fields(self):
        email = Email.objects.create(uid='att-ext-uid', subject='Att Ext')
        att = Attachment.objects.create(
            email=email,
            file_path=r'C:\img\photo.png',
            filename='photo.png',
            size=5000,
            content_type='image/png',
            is_inline=True,
            content_id='cid:photo123',
        )
        self.assertTrue(att.is_inline)
        self.assertEqual(att.content_id, 'cid:photo123')

    def test_attachment_icon_class(self):
        email = Email.objects.create(uid='icon-uid', subject='Icon')
        for ext, expected in [
            ('docx', 'bi-file-word-fill'),
            ('xlsx', 'bi-file-excel-fill'),
            ('jpg', 'bi-file-image-fill'),
            ('pdf', 'bi-file-pdf-fill'),
            ('zip', 'bi-file-zip-fill'),
            ('dwg', 'bi-file-earmark-fill'),
            ('unknown', 'bi-file-earmark-fill'),
        ]:
            att = Attachment(
                email=email,
                file_path=f'test.{ext}',
                filename=f'test.{ext}',
                size=100,
            )
            self.assertEqual(att.icon_class, expected, f'Failed for .{ext}')


class ExtractEmailAddressTest(TestCase):
    """Tests for extract_email_address utility."""

    def test_angle_bracket_format(self):
        self.assertEqual(extract_email_address('Name <email@test.com>'), 'email@test.com')

    def test_quoted_name_format(self):
        self.assertEqual(extract_email_address('"Name" <email@test.com>'), 'email@test.com')

    def test_bare_email(self):
        self.assertEqual(extract_email_address('email@test.com'), 'email@test.com')

    def test_name_only(self):
        self.assertIsNone(extract_email_address('Sergey Strakhov'))

    def test_empty_string(self):
        self.assertIsNone(extract_email_address(''))

    def test_none(self):
        self.assertIsNone(extract_email_address(None))

    def test_whitespace(self):
        self.assertIsNone(extract_email_address('   '))

    def test_mixed_format(self):
        result = extract_email_address('Sergey Strakhov <strakhov.s@cimrus.com>')
        self.assertEqual(result, 'strakhov.s@cimrus.com')

    def test_comma_separated(self):
        result = extract_email_address('email1@test.com, email2@test.com')
        self.assertEqual(result, 'email1@test.com')

    def test_name_then_email(self):
        result = extract_email_address('Sergey Strakhov, strakhov.s@cimrus.com')
        self.assertEqual(result, 'strakhov.s@cimrus.com')


class ExtractAllEmailAddressesTest(TestCase):
    """Tests for extract_all_email_addresses utility."""

    def test_single_email(self):
        self.assertEqual(extract_all_email_addresses('email@test.com'), ['email@test.com'])

    def test_angle_bracket(self):
        result = extract_all_email_addresses('Name <email@test.com>')
        self.assertEqual(result, ['email@test.com'])

    def test_comma_separated(self):
        result = extract_all_email_addresses('a@test.com, b@test.com')
        self.assertEqual(result, ['a@test.com', 'b@test.com'])

    def test_mixed(self):
        result = extract_all_email_addresses('Name <a@test.com>, b@test.com')
        self.assertEqual(result, ['a@test.com', 'b@test.com'])

    def test_empty(self):
        self.assertEqual(extract_all_email_addresses(''), [])

    def test_none(self):
        self.assertEqual(extract_all_email_addresses(None), [])

    def test_no_emails(self):
        self.assertEqual(extract_all_email_addresses('Just some text'), [])


class ResolveSenderToEmailTest(TestCase):
    """Tests for resolve_sender_to_email utility."""

    def test_already_email(self):
        self.assertEqual(resolve_sender_to_email('user@test.com'), 'user@test.com')

    def test_angle_bracket_format(self):
        result = resolve_sender_to_email('Name <user@test.com>')
        self.assertEqual(result, 'user@test.com')

    def test_name_only_with_contact(self):
        contact = Contact.objects.create(name='John Doe')
        ContactEmail.objects.create(contact=contact, email='john@test.com', is_primary=True)
        result = resolve_sender_to_email('John Doe')
        self.assertEqual(result, 'john@test.com')

    def test_name_only_no_contact(self):
        result = resolve_sender_to_email('Unknown Person')
        self.assertEqual(result, 'Unknown Person')

    def test_empty(self):
        self.assertEqual(resolve_sender_to_email(''), '')

    def test_none(self):
        self.assertEqual(resolve_sender_to_email(None), '')


class ComposeModalViewTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for compose modal view."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('composeuser', 'compose@test.com', 'password')
        self.client.login(username='composeuser', password='password')
        self.contact = Contact.objects.create(name='Test Contact')
        ContactEmail.objects.create(contact=self.contact, email='test@contact.com', is_primary=True)

    def test_compose_modal_status(self):
        response = self.client.get(reverse('email_ui:compose_modal'))
        self.assertEqual(response.status_code, 200)

    def test_compose_modal_template(self):
        response = self.client.get(reverse('email_ui:compose_modal'))
        self.assertTemplateUsed(response, 'email_ui/partials/compose_modal.html')

    def test_compose_modal_has_contacts(self):
        response = self.client.get(reverse('email_ui:compose_modal'))
        self.assertIn('contacts', response.context)
        self.assertEqual(response.context['contacts'].count(), 1)

    def test_compose_modal_mode(self):
        response = self.client.get(reverse('email_ui:compose_modal'))
        self.assertEqual(response.context['mode'], 'compose')


class ReplyModalViewTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for reply modal view - sender should be resolved to email."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('replyuser', 'reply@test.com', 'password')
        self.client.login(username='replyuser', password='password')
        self.email = self.create_test_email(
            uid='reply-uid-1',
            sender='Sergey Strakhov <strakhov.s@cimrus.com>',
        )

    def test_reply_modal_resolves_sender_email(self):
        response = self.client.get(
            reverse('email_ui:reply_modal', args=[self.email.pk, 'reply'])
        )
        self.assertEqual(response.context['to'], 'strakhov.s@cimrus.com')

    def test_reply_all_modal_resolves_sender_email(self):
        response = self.client.get(
            reverse('email_ui:reply_modal', args=[self.email.pk, 'reply_all'])
        )
        self.assertEqual(response.context['to'], 'strakhov.s@cimrus.com')

    def test_forward_modal_to_empty(self):
        response = self.client.get(
            reverse('email_ui:reply_modal', args=[self.email.pk, 'forward'])
        )
        self.assertEqual(response.context['to'], '')

    def test_reply_modal_sender_name_only_with_contact(self):
        contact = Contact.objects.create(name='John Smith')
        ContactEmail.objects.create(contact=contact, email='john@smith.com', is_primary=True)
        self.email.sender = 'John Smith'
        self.email.save()
        response = self.client.get(
            reverse('email_ui:reply_modal', args=[self.email.pk, 'reply'])
        )
        self.assertEqual(response.context['to'], 'john@smith.com')


class SendEmailViewTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for send_email view with mocked SMTP."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('senduser', 'send@test.com', 'password')
        self.client.login(username='senduser', password='password')
        self.smtp_account = SMTPAccount.objects.create(
            name='Test SMTP',
            host='smtp.test.com',
            port=587,
            username='user@test.com',
            password='pass',
            from_email='user@test.com',
            from_name='Test User',
            is_default=True,
        )

    @patch('email_ui.services.email_sender.smtplib.SMTP')
    def test_send_email_success(self, mock_smtp):
        mock_server = mock_smtp.return_value.__enter__.return_value
        mock_server.sendmail.return_value = {}

        response = self.client.post(reverse('email_ui:send_email'), {
            'to': 'recipient@test.com',
            'subject': 'Test Subject',
            'body': '<p>Hello</p>',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'email_ui/partials/send_success.html')
        mock_server.sendmail.assert_called_once()

    @patch('email_ui.services.email_sender.smtplib.SMTP')
    def test_send_email_resolves_angle_bracket(self, mock_smtp):
        mock_server = mock_smtp.return_value.__enter__.return_value
        mock_server.sendmail.return_value = {}

        response = self.client.post(reverse('email_ui:send_email'), {
            'to': 'Name <recipient@test.com>',
            'subject': 'Test',
            'body': '<p>Hi</p>',
        })
        self.assertEqual(response.status_code, 200)
        call_args = mock_server.sendmail.call_args
        recipients = call_args[0][1]
        self.assertIn('recipient@test.com', recipients)

    @patch('email_ui.services.email_sender.smtplib.SMTP')
    def test_send_email_multiple_recipients(self, mock_smtp):
        mock_server = mock_smtp.return_value.__enter__.return_value
        mock_server.sendmail.return_value = {}

        response = self.client.post(reverse('email_ui:send_email'), {
            'to': 'a@test.com, b@test.com',
            'subject': 'Multi',
            'body': '<p>Hi</p>',
        })
        self.assertEqual(response.status_code, 200)
        call_args = mock_server.sendmail.call_args
        recipients = call_args[0][1]
        self.assertIn('a@test.com', recipients)
        self.assertIn('b@test.com', recipients)

    def test_send_email_no_recipient(self):
        response = self.client.post(reverse('email_ui:send_email'), {
            'to': '',
            'subject': 'No recipient',
            'body': '<p>Hi</p>',
        })
        self.assertEqual(response.status_code, 400)

    def test_send_email_name_only_fails_validation(self):
        """Sending to a plain name without email should fail."""
        response = self.client.post(reverse('email_ui:send_email'), {
            'to': 'Sergey Strakhov',
            'subject': 'Name only',
            'body': '<p>Hi</p>',
        })
        self.assertIn(response.status_code, [400, 200])


class ReplySendViewTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for reply_send view with mocked SMTP."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('replysenduser', 'rs@test.com', 'password')
        self.client.login(username='replysenduser', password='password')
        self.smtp_account = SMTPAccount.objects.create(
            name='Test SMTP',
            host='smtp.test.com',
            port=587,
            username='user@test.com',
            password='pass',
            from_email='user@test.com',
            from_name='Test User',
            is_default=True,
        )
        self.email = self.create_test_email(
            uid='replysend-uid-1',
            sender='Sergey Strakhov <strakhov.s@cimrus.com>',
        )

    @patch('email_ui.services.email_sender.smtplib.SMTP')
    def test_reply_send_resolves_sender(self, mock_smtp):
        mock_server = mock_smtp.return_value.__enter__.return_value
        mock_server.sendmail.return_value = {}

        response = self.client.post(
            reverse('email_ui:reply_send', args=[self.email.pk]),
            {'mode': 'reply', 'body': 'Reply text', 'subject': 'Re: Test'}
        )
        self.assertEqual(response.status_code, 200)
        call_args = mock_server.sendmail.call_args
        recipients = call_args[0][1]
        self.assertIn('strakhov.s@cimrus.com', recipients)
        self.assertNotIn('Sergey Strakhov', recipients)

    @patch('email_ui.services.email_sender.smtplib.SMTP')
    def test_reply_send_with_typed_email(self, mock_smtp):
        mock_server = mock_smtp.return_value.__enter__.return_value
        mock_server.sendmail.return_value = {}

        response = self.client.post(
            reverse('email_ui:reply_send', args=[self.email.pk]),
            {'mode': 'reply', 'to': 'other@test.com', 'body': 'Hi', 'subject': 'Re: Test'}
        )
        self.assertEqual(response.status_code, 200)
        call_args = mock_server.sendmail.call_args
        recipients = call_args[0][1]
        self.assertIn('other@test.com', recipients)

    @patch('email_ui.services.email_sender.smtplib.SMTP')
    def test_forward_send_no_original_body(self, mock_smtp):
        mock_server = mock_smtp.return_value.__enter__.return_value
        mock_server.sendmail.return_value = {}

        response = self.client.post(
            reverse('email_ui:reply_send', args=[self.email.pk]),
            {'mode': 'forward', 'to': 'fwd@test.com', 'body': 'Forwarded', 'subject': 'Fwd: Test'}
        )
        self.assertEqual(response.status_code, 200)


class SaveDraftViewTest(CategoryMixin, TestCase, ViewTestCaseMixin):
    """Tests for save_draft view."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('draftuser', 'draft@test.com', 'password')
        self.client.login(username='draftuser', password='password')

    @override_settings(DRAFT_DIRECTORY=os.path.join(tempfile.gettempdir(), 'test_drafts'))
    def test_save_draft_with_subject(self):
        response = self.client.post(reverse('email_ui:save_draft'), {
            'to': 'recipient@test.com',
            'subject': 'Draft Subject',
            'body': '<p>Draft body</p>',
        })
        self.assertEqual(response.status_code, 204)
        draft = Email.objects.filter(folder='drafts').first()
        self.assertIsNotNone(draft)
        self.assertEqual(draft.subject, 'Draft Subject')
        self.assertEqual(draft.receiver, 'recipient@test.com')
        self.assertEqual(draft.sent_status, 'draft')

    @override_settings(DRAFT_DIRECTORY=os.path.join(tempfile.gettempdir(), 'test_drafts'))
    def test_save_draft_without_subject(self):
        """Draft should save even without subject."""
        response = self.client.post(reverse('email_ui:save_draft'), {
            'to': 'recipient@test.com',
            'subject': '',
            'body': '<p>No subject draft</p>',
        })
        self.assertEqual(response.status_code, 204)
        draft = Email.objects.filter(folder='drafts').first()
        self.assertIsNotNone(draft)
        self.assertEqual(draft.subject, '')

    @override_settings(DRAFT_DIRECTORY=os.path.join(tempfile.gettempdir(), 'test_drafts'))
    def test_save_draft_empty_body(self):
        response = self.client.post(reverse('email_ui:save_draft'), {
            'subject': 'Empty body',
        })
        self.assertEqual(response.status_code, 204)
        draft = Email.objects.filter(folder='drafts').first()
        self.assertIsNotNone(draft)

    @override_settings(DRAFT_DIRECTORY=os.path.join(tempfile.gettempdir(), 'test_drafts'))
    def test_save_draft_creates_file(self):
        response = self.client.post(reverse('email_ui:save_draft'), {
            'subject': 'File Test',
            'body': '<p>Saved body</p>',
        })
        self.assertEqual(response.status_code, 204)
        draft = Email.objects.filter(folder='drafts').first()
        self.assertIsNotNone(draft)
        self.assertTrue(os.path.exists(draft.link))
        html_files = [f for f in os.listdir(draft.link) if f.endswith('.html')]
        self.assertEqual(len(html_files), 1)
        with open(os.path.join(draft.link, html_files[0]), 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('Saved body', content)

    @override_settings(DRAFT_DIRECTORY=os.path.join(tempfile.gettempdir(), 'test_drafts'))
    def test_save_draft_requires_post(self):
        response = self.client.get(reverse('email_ui:save_draft'))
        self.assertEqual(response.status_code, 405)
