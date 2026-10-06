# -*- coding: utf-8 -*-
"""F2: characterization-тесты email_ui — фиксируют ФАКТ до рефакторинга.

Покрывают пробелы: матрица to/cc/bcc, вложения на диск, bulk select_all
vs явные id, copy_email, do_export. Не дублируют существующие
SendEmailViewTest/ReplySendViewTest/Draft* (email_ui/tests.py).
"""
import os
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from Emails.models import Attachment, Email
from ProjectContract.models import Contractor
from StaticData.models import Category, ProjectSite, Status
from email_ui.models import SMTPAccount
from email_ui.services.email_sender import EmailSenderService


class RefMixin:
    """Справочники pk=1 под FK-дефолты (как CategoryMixin в tests.py)."""

    @classmethod
    def _ensure_refs(cls):
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})


class SendGuardMixin(RefMixin):
    @classmethod
    def setUpTestData(cls):
        cls._ensure_refs()
        cls.user = User.objects.create_user(
            username='f2_sender', password='pw', email='me@corp.com')
        cls.smtp = SMTPAccount.objects.create(
            name='F2 SMTP', host='smtp.test.com', port=587,
            username='user@test.com', password='pass',
            from_email='user@test.com', from_name='F2', is_default=True)

    def setUp(self):
        self.client.force_login(self.user)
        _imap_mock = patch.object(EmailSenderService, '_save_copy_to_imap_sent')
        _imap_mock.start()
        self.addCleanup(_imap_mock.stop)
        _smtp_mock = patch('email_ui.services.email_sender.smtplib.SMTP')
        self.mock_smtp_cls = _smtp_mock.start()
        self.addCleanup(_smtp_mock.stop)
        self.mock_server = self.mock_smtp_cls.return_value.__enter__.return_value
        self.mock_server.sendmail.return_value = {}

    def _send(self, **over):
        data = {'to': 'a@test.com', 'subject': 'F2', 'body': '<p>Hi</p>'}
        data.update(over)
        return self.client.post(reverse('email_ui:send_email'), data)


class SendMatrixGuardsTest(SendGuardMixin, TestCase):
    def test_semicolon_separated_to(self):
        # Факт: send понимает ';' (как и draft_send) — оба адреса уходят в SMTP.
        resp = self._send(to='a@test.com; b@test.com')
        self.assertEqual(resp.status_code, 200)
        recipients = self.mock_server.sendmail.call_args[0][1]
        self.assertIn('a@test.com', recipients)
        self.assertIn('b@test.com', recipients)

    def test_invalid_address_400_same_template(self):
        # Факт: невалидный адрес -> 400 + тот же compose_modal (не редирект).
        resp = self._send(to='not-an-email')
        self.assertEqual(resp.status_code, 400)
        self.assertTemplateUsed(resp, 'email_ui/partials/compose_modal.html')

    def test_cc_bcc_stored_on_record(self):
        # Факт: cc/bcc кладутся в запись строкой через ', '.
        resp = self._send(to='a@test.com', cc='c@test.com', bcc='h@test.com')
        self.assertEqual(resp.status_code, 200)
        email = Email.objects.get(folder='sent', subject='F2')
        self.assertEqual(email.cc, 'c@test.com')
        self.assertEqual(email.bcc, 'h@test.com')
        self.assertEqual(email.sent_status, 'sent')
        self.assertTrue(email.is_read)


class SendAttachmentGuardsTest(SendGuardMixin, TestCase):
    def test_attachment_record_without_link_no_file(self):
        # Файлы без link складываются в E_MAIL_DIRECTORY/sent/<id>
        # (раньше молча терялись с file_path == '').
        import tempfile
        content = b'%PDF-1.4 fake'
        with tempfile.TemporaryDirectory() as tmp:
            with patch('email_ui.services.compose_service.E_MAIL_DIRECTORY', tmp):
                resp = self.client.post(reverse('email_ui:send_email'), {
                    'to': 'a@test.com', 'subject': 'F2files', 'body': '<p>x</p>',
                    'attachment_files': SimpleUploadedFile(
                        'doc.pdf', content, content_type='application/pdf'),
                })
                self.assertEqual(resp.status_code, 200)
                email = Email.objects.get(folder='sent', subject='F2files')
                att = Attachment.objects.get(email=email, filename='doc.pdf')
                self.assertEqual(att.size, len(content))
                self.assertTrue(att.file_path.startswith(tmp))
                email.refresh_from_db()
                self.assertTrue(email.link.startswith(tmp))
                with open(att.file_path, 'rb') as fh:
                    self.assertEqual(fh.read(), content)


class BulkGuardsTest(RefMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._ensure_refs()
        cls.user = User.objects.create_user(username='f2_bulk', password='pw')

    def setUp(self):
        self.client.force_login(self.user)
        self.ids = [
            Email.objects.create(
                uid=f'f2-bulk-{i}', subject=f'B{i}',
                sender='s@test.com', folder='inbox').pk
            for i in range(3)]

    def _mark_important(self, **over):
        data = {'action': 'mark_important', 'folder': 'inbox'}
        data.update(over)
        return self.client.post(reverse('email_ui:bulk_action'), data)

    def test_select_all_marks_everything(self):
        resp = self._mark_important(select_all='1', filter_params='')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            Email.objects.filter(pk__in=self.ids, is_important=True).count(), 3)

    def test_select_all_equals_explicit_ids(self):
        # Гард: select_all=1 и явный список всех id дают одно множество.
        self._mark_important(select_all='1', filter_params='')
        via_all = set(Email.objects.filter(
            pk__in=self.ids, is_important=True).values_list('pk', flat=True))
        Email.objects.filter(pk__in=self.ids).update(is_important=False)
        self._mark_important(selected_emails=[str(i) for i in self.ids])
        via_explicit = set(Email.objects.filter(
            pk__in=self.ids, is_important=True).values_list('pk', flat=True))
        self.assertEqual(via_all, via_explicit)
        self.assertEqual(via_all, set(self.ids))

    def test_unknown_action_400(self):
        resp = self._mark_important(action='hack_the_planet',
                                    selected_emails=[str(self.ids[0])])
        self.assertEqual(resp.status_code, 400)


class CopyEmailGuardsTest(RefMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._ensure_refs()
        cls.user = User.objects.create_user(username='f2_copy', password='pw')
        cls.site = ProjectSite.objects.create(name='F2-Объект')
        cls.contractor = Contractor.objects.create(name='F2-Подрядчик')

    def setUp(self):
        self.client.force_login(self.user)

    def test_without_project_redirects_with_error(self):
        # Факт: без проекта/подрядчика — 302 + messages.error, без исключений.
        email = Email.objects.create(
            uid='f2-copy-naked', subject='Naked',
            sender='s@test.com', folder='inbox')
        resp = self.client.post(
            reverse('email_ui:copy_email', args=[email.pk]), follow=True)
        self.assertEqual(resp.status_code, 200)
        msgs = [str(m) for m in resp.context['messages']]
        self.assertTrue(any('проект и подрядчика' in m for m in msgs))

    def test_with_project_creates_dir(self):
        # Факт: путь строится из E_MAIL_DIRECTORY/проект/подрядчик/тип/год.
        # E_MAIL_DIRECTORY импортирован в views по значению — патчим атрибут.
        email = Email.objects.create(
            uid='f2-copy-full', subject='Full', sender='s@test.com',
            folder='inbox', project_site=self.site,
            contractor=self.contractor, email_type='IN')
        with tempfile.TemporaryDirectory() as tmp:
            with patch('email_ui.views.E_MAIL_DIRECTORY', tmp):
                resp = self.client.post(
                    reverse('email_ui:copy_email', args=[email.pk]))
                self.assertEqual(resp.status_code, 302)
                self.assertTrue(os.path.isdir(
                    os.path.join(tmp, 'F2-Объект', 'F2-Подрядчик')))


class ComposeServiceTest(TestCase):
    """Юнит-тесты email_ui.services.compose_service (блок 3)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='f2_svc', password='pw')
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})

    def test_parse_recipients_variants(self):
        from email_ui.services.compose_service import parse_recipients
        self.assertEqual(parse_recipients('a@test.com; b@test.com'),
                         ['a@test.com', 'b@test.com'])
        self.assertEqual(parse_recipients('Name <a@test.com>'), ['a@test.com'])
        self.assertEqual(parse_recipients('a@test.com, b@test.com'),
                         ['a@test.com', 'b@test.com'])
        self.assertEqual(parse_recipients(''), [])

    def test_invalid_addresses(self):
        from email_ui.services.compose_service import invalid_addresses
        self.assertEqual(invalid_addresses(['a@test.com', 'nope']), ['nope'])
        self.assertEqual(invalid_addresses([]), [])

    def test_parse_excluded_ids_skips_garbage(self):
        from django.http import QueryDict
        from email_ui.services.compose_service import parse_excluded_ids
        qd = QueryDict('exclude_attachments=5&exclude_attachments=abc')
        self.assertEqual(parse_excluded_ids(qd), {5})

    def test_create_sent_email_and_copies(self):
        from email_ui.services.compose_service import (
            copy_attachment_rows, create_sent_email, persist_uploaded_files)
        sender = EmailSenderService()
        sent = create_sent_email(
            sender=sender, subject='S', to_list=['a@test.com'],
            cc_list=['c@test.com'], bcc_list=[])
        self.assertEqual(sent.folder, 'sent')
        self.assertEqual(sent.receiver, 'a@test.com')
        self.assertEqual(sent.cc, 'c@test.com')
        self.assertIsNone(sent.bcc)
        src = Email.objects.create(uid='f2-svc-src', sender='s@t.com', folder='inbox')
        att = Attachment.objects.create(email=src, filename='f.txt', size=3)
        copy_attachment_rows(sent, [att], set())
        self.assertEqual(
            Attachment.objects.get(email=sent, filename='f.txt').size, 3)
        copy_attachment_rows(sent, [att], {att.pk})  # excluded — дубля нет
        self.assertEqual(Attachment.objects.filter(email=sent).count(), 1)
        # Без link файл уходит в fallback E_MAIL_DIRECTORY/sent/<id>.
        import os as _os
        import tempfile
        from unittest.mock import patch as _patch
        with tempfile.TemporaryDirectory() as tmp:
            with _patch('email_ui.services.compose_service.E_MAIL_DIRECTORY', tmp):
                persist_uploaded_files(sent, [SimpleUploadedFile('n.txt', b'123')])
                row = Attachment.objects.get(email=sent, filename='n.txt')
                self.assertTrue(row.file_path.startswith(tmp))
                self.assertTrue(_os.path.isfile(row.file_path))
                self.assertEqual(row.size, 3)


class FetchGuardsTest(TestCase):
    """Получение почты: мусор и падение IMAP не дают 500 (баг 2026-10-06)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='f2_fetch', password='pw')

    def setUp(self):
        self.client.force_login(self.user)
        _parser_mock = patch('email_ui.views.ParsingImapEmailToDB')
        self.mock_parser_cls = _parser_mock.start()
        self.addCleanup(_parser_mock.stop)
        inst = self.mock_parser_cls.return_value
        inst.create_action_list = []
        inst.skip_action_list = []
        inst.error_list = []

    def _post(self, **over):
        data = {'mail_count': '1'}
        data.update(over)
        return self.client.post(reverse('email_ui:fetch_emails'), data)

    def test_garbage_count_falls_back_to_default(self):
        resp = self._post(mail_count='мусор')
        self.assertEqual(resp.status_code, 302)
        self.mock_parser_cls.return_value.main.assert_called()
        _, kwargs = self.mock_parser_cls.return_value.main.call_args
        self.assertEqual(kwargs.get('limit'), 10)

    def test_huge_count_clamped(self):
        resp = self._post(mail_count='999999')
        self.assertEqual(resp.status_code, 302)
        _, kwargs = self.mock_parser_cls.return_value.main.call_args
        self.assertEqual(kwargs.get('limit'), 500)

    def test_folder_crash_becomes_warning(self):
        self.mock_parser_cls.return_value.main.side_effect = ConnectionError('BYE')
        resp = self.client.post(reverse('email_ui:fetch_emails'), {'mail_count': '1'})
        self.assertEqual(resp.status_code, 302)
        page = self.client.get(resp.get('Location'), follow=True)
        self.assertEqual(page.status_code, 200)
        msgs = [str(m) for m in page.context['messages']]
        self.assertTrue(any('BYE' in m for m in msgs))


class ScheduledFetchTest(TestCase):
    """Автозагрузка: падение одной папки не отменяет вторую (блок 14)."""

    def _run(self, side_effects):
        from email_ui import scheduled as sched_mod
        with patch.object(sched_mod, 'ParsingImapEmailToDB') as mock_cls:
            inst = mock_cls.return_value
            inst.create_action_list = ['u1']
            inst.skip_action_list = []
            inst.error_list = []
            inst.main.side_effect = side_effects
            sched_mod.fetch_new_emails_job()
            return inst.main

    def test_second_folder_survives_first_crash(self):
        main = self._run([ConnectionError('BYE'), None])
        self.assertEqual(main.call_count, 2)

    def test_success_no_raise(self):
        main = self._run(None)
        self.assertEqual(main.call_count, 2)


class ExportGuardsTest(RefMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._ensure_refs()
        cls.user = User.objects.create_user(username='f2_export', password='pw')

    def setUp(self):
        self.client.force_login(self.user)
        self.email = Email.objects.create(
            uid='f2-export-1', subject='Exp', sender='s@test.com',
            folder='inbox')

    def test_export_without_ids_400(self):
        resp = self.client.post(reverse('email_ui:do_export'), {
            'export_format': 'eml', 'organize_by': 'date'})
        self.assertEqual(resp.status_code, 400)

    def test_export_eml_redirects_and_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('email_ui.views.E_MAIL_DIRECTORY', tmp):
                resp = self.client.post(reverse('email_ui:do_export'), {
                    'selected_emails': [str(self.email.pk)],
                    'export_format': 'eml', 'organize_by': 'date'})
                self.assertEqual(resp.status_code, 302)
                exports = os.path.join(tmp, 'exports')
                self.assertTrue(os.path.isdir(exports))
                self.assertTrue(any(
                    f.startswith('export_') for f in os.listdir(exports)))
