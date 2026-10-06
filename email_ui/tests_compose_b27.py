"""Блок 27 (B1): гарды шагов compose-потока (services/compose_flow).

Пины поведения, вынесенного из views 1:1: пикер, reply_all-исключения,
фолбэки получателей/темы, сбор вложений, записи вложений черновика,
каталог черновика.
"""
import os
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings

from Emails.models import Attachment, Email
from email_ui.models import (
    Contact, ContactEmail, ContactGroup, SMTPAccount,
)
from email_ui.services import compose_flow as flow


class PickerTest(TestCase):
    def setUp(self):
        self.c1 = Contact.objects.create(name='A', is_active=True)
        ContactEmail.objects.create(
            contact=self.c1, email='a@test.com', is_primary=True)
        self.c2 = Contact.objects.create(name='A-dup', is_active=True)
        ContactEmail.objects.create(
            contact=self.c2, email='A@TEST.com', is_primary=True)
        self.c3 = Contact.objects.create(name='NoMail', is_active=True)
        self.off = Contact.objects.create(name='Off', is_active=False)
        ContactEmail.objects.create(
            contact=self.off, email='off@test.com', is_primary=True)

    def test_active_contacts_only(self):
        qs = flow.active_contacts()
        self.assertIn(self.c1, qs)
        self.assertNotIn(self.off, qs)

    def test_picker_dedups_case_insensitive(self):
        out = flow.contacts_picker_json(flow.active_contacts())
        mails = [r['e'] for r in out]
        self.assertEqual(len(mails), len({m.lower() for m in mails}))
        self.assertIn('a@test.com', [m.lower() for m in mails])

    def test_picker_skips_contact_without_email(self):
        out = flow.contacts_picker_json(flow.active_contacts())
        self.assertNotIn('NoMail', [r['n'] for r in out])

    def test_picker_context_keys(self):
        contacts = flow.active_contacts()
        ctx = flow.picker_context(contacts)
        self.assertEqual(set(ctx), {'contacts', 'contacts_json', 'groups_json'})
        self.assertIs(ctx['contacts'], contacts)
        self.assertEqual(
            ctx['contacts_json'], flow.contacts_picker_json(contacts))

    def test_groups_picker(self):
        g = ContactGroup.objects.create(name='G1', is_active=True)
        g.contacts.add(self.c1)
        ContactGroup.objects.create(name='G-off', is_active=False)
        out = flow.groups_picker_json()
        names = [r['n'] for r in out]
        self.assertIn('G1', names)
        self.assertNotIn('G-off', names)
        g1 = [r for r in out if r['n'] == 'G1'][0]
        self.assertIn('a@test.com', [e.lower() for e in g1['e']])


class ReplyAllTest(TestCase):
    def setUp(self):
        from StaticData.models import Category, Status
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        SMTPAccount.objects.create(
            name='S1', host='s', from_email='robot@test.com', is_active=True)
        self.email = Email.objects.create(
            uid='b27-a', subject='S', sender='boss <boss@test.com>',
            receiver='me@test.com, robot@test.com, Без почты',
            cc='boss@test.com, pal@test.com',
            email_type='IN', folder='inbox', sent_status='sent')

    def test_to_is_sender_cc_excludes_self_and_smtp(self):
        to, cc, missing = flow.reply_all_recipients(
            self.email, 'me@test.com')
        self.assertEqual(to, 'boss@test.com')
        cc_list = [c.strip() for c in cc.split(',') if c.strip()]
        self.assertIn('pal@test.com', cc_list)
        self.assertNotIn('boss@test.com', cc_list)
        self.assertNotIn('robot@test.com', cc_list)
        self.assertNotIn('me@test.com', cc_list)
        self.assertIn('Без почты', missing)


class ResolveRecipientsTest(TestCase):
    def setUp(self):
        from StaticData.models import Category, Status
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        self.email = Email.objects.create(
            uid='b27-b', subject='S', sender='boss@test.com',
            receiver='me@test.com', cc='pal@test.com',
            email_type='IN', folder='inbox', sent_status='sent')

    def test_reply_falls_back_to_sender(self):
        to, _cc = flow.resolve_reply_recipients(
            self.email, '', '', 'reply', 'me@test.com')
        self.assertEqual(to, ['boss@test.com'])

    def test_forward_no_fallback(self):
        to, _cc = flow.resolve_reply_recipients(
            self.email, '', '', 'forward', 'me@test.com')
        self.assertEqual(to, [])

    def test_reply_all_cc_fallback(self):
        _to, cc = flow.resolve_reply_recipients(
            self.email, 'boss@test.com', '', 'reply_all', 'me@test.com')
        self.assertIn('pal@test.com', cc)
        self.assertNotIn('me@test.com', cc)

    def test_explicit_values_kept_invalid_dropped(self):
        to, _cc = flow.resolve_reply_recipients(
            self.email, 'ok@test.com, not-an-email', '', 'reply', '')
        self.assertEqual(to, ['ok@test.com'])

    def test_user_email_helper(self):
        rf = RequestFactory()
        user = User.objects.create_user('u27', 'Me@TEST.com', 'pw')
        req = rf.get('/fake/')
        req.user = user
        self.assertEqual(flow.current_user_email(req), 'me@test.com')
        req2 = rf.get('/fake/')
        req2.user = None
        self.assertEqual(flow.current_user_email(req2), '')


class ResolveSubjectTest(TestCase):
    def test_keeps_entered(self):
        self.assertEqual(flow.resolve_subject('Old', 'New', 'reply'), 'New')

    def test_reply_default(self):
        self.assertEqual(flow.resolve_subject('Hi', '', 'reply'), 'Re: Hi')
        self.assertEqual(flow.resolve_subject('', '', 'reply_all'), 'Re:')

    def test_forward_default(self):
        self.assertEqual(flow.resolve_subject('Hi', '', 'forward'), 'Fwd: Hi')
        self.assertEqual(flow.resolve_subject('', '', 'forward'), 'Fwd:')


class CollectAttachmentsTest(TestCase):
    def setUp(self):
        from StaticData.models import Category, Status
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        self.email = Email.objects.create(
            uid='b27-c', subject='S', sender='a@t.co',
            email_type='IN', folder='inbox', sent_status='sent')
        self.a1 = Attachment.objects.create(
            email=self.email, filename='a.txt', file_path='/tmp/a.txt',
            size=1, content_type='text/plain')
        self.a2 = Attachment.objects.create(
            email=self.email, filename='b.txt', file_path='/tmp/b.txt',
            size=2, content_type='text/plain')

    def test_excluded_skipped_uploaded_appended(self):
        up = SimpleUploadedFile('n.txt', b'x')
        out = flow.collect_reply_attachments(
            self.email, True, {self.a1.pk}, [up])
        self.assertNotIn(self.a1, out)
        self.assertIn(self.a2, out)
        self.assertIn(up, out)

    def test_no_include_only_uploaded(self):
        up = SimpleUploadedFile('n.txt', b'x')
        out = flow.collect_reply_attachments(
            self.email, False, set(), [up])
        self.assertEqual(out, [up])


class RecordDraftAttachmentsTest(TestCase):
    def setUp(self):
        from StaticData.models import Category, Status
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        self.draft = Email.objects.create(
            uid='b27-d', subject='S', sender='', email_type='OUT',
            folder='drafts', sent_status='draft')
        self.sent = Email.objects.create(
            uid='b27-e', subject='S', sender='', email_type='OUT',
            folder='sent', sent_status='sent')
        self.old = Attachment.objects.create(
            email=self.draft, filename='o.txt', file_path='/tmp/o.txt',
            size=3, content_type='text/plain')

    def test_existing_copied_as_new_row(self):
        flow.record_draft_attachments(self.sent, [self.old])
        rows = Attachment.objects.filter(email=self.sent)
        self.assertEqual(rows.count(), 1)
        self.assertNotEqual(rows[0].pk, self.old.pk)
        self.assertEqual(rows[0].filename, 'o.txt')

    def test_uploaded_persisted_to_tmp_maildir(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                'email_ui.services.compose_service.E_MAIL_DIRECTORY', tmp,
            ):
                up = SimpleUploadedFile('u.txt', b'data')
                flow.record_draft_attachments(self.sent, [up])
        row = Attachment.objects.filter(email=self.sent).first()
        self.assertIsNotNone(row)
        self.assertTrue(row.file_path.startswith(tmp))


class PrepareDraftDirTest(TestCase):
    def test_creates_dir_and_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(DRAFT_DIRECTORY=tmp):
                d = flow.prepare_draft_dir('Тема!', '<p>hi</p>')
                self.assertTrue(os.path.isdir(d))
                files = os.listdir(d)
                self.assertEqual(len(files), 1)
                with open(os.path.join(d, files[0]), encoding='utf-8') as f:
                    self.assertIn('hi', f.read())

    def test_empty_body_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(DRAFT_DIRECTORY=tmp):
                d = flow.prepare_draft_dir('Subj', '')
                self.assertTrue(os.path.isdir(d))
                self.assertEqual(os.listdir(d), [])
