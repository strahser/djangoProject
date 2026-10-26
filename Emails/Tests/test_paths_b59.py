# -*- coding: utf-8 -*-
"""Пути архива: разрешение старого корня и команда rewrite_email_paths.

История: база хранит абсолютные пути, корень архива переехал с e:\\ на d:\\.
Читающий код перебазирует устаревшие пути на текущий E_MAIL_DIRECTORY,
а команда rewrite_email_paths чистит сами записи в БД.
"""
import os
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings

from Emails.models import Attachment, Email
from Emails.paths import replace_drive, resolve_email_path, split_archive_tail

OLD_ROOT = r'e:\Проекты Симрус\Переписка\Bitrix 24'
NEW_ROOT = r'd:\Проекты Симрус\Переписка\Bitrix 24'


class ResolveEmailPathTest(TestCase):
    def test_empty_path(self):
        self.assertEqual(resolve_email_path(''), '')
        self.assertIsNone(resolve_email_path(None))

    def test_existing_path_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(resolve_email_path(tmp), tmp)

    def test_split_tail(self):
        path = OLD_ROOT + r'\imap_attachments\INBOX\1\file.pdf'
        self.assertEqual(
            split_archive_tail(path),
            r'imap_attachments\INBOX\1\file.pdf')
        self.assertIsNone(split_archive_tail(r'C:\temp\x.txt'))
        self.assertEqual(split_archive_tail(r'D:\x\sent\5\body.html'),
                         r'sent\5\body.html')

    def test_old_root_rebased(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'imap_attachments' / 'INBOX' / '1'
            folder.mkdir(parents=True)
            target = folder / 'file.pdf'
            target.write_bytes(b'x')

            with override_settings(E_MAIL_DIRECTORY=tmp):
                resolved = resolve_email_path(
                    OLD_ROOT + r'\imap_attachments\INBOX\1\file.pdf')

            self.assertEqual(os.path.normcase(resolved),
                             os.path.normcase(str(target)))

    def test_old_path_without_bitrix_rebased_to_parent(self):
        """Старый архив лежал прямо в «Переписка», без «Bitrix 24»."""
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'imap_attachments' / 'INBOX' / '2'
            folder.mkdir(parents=True)
            target = folder / 'x.pdf'
            target.write_bytes(b'x')
            current_root = Path(tmp) / 'Bitrix 24'
            current_root.mkdir()

            with override_settings(E_MAIL_DIRECTORY=str(current_root)):
                resolved = resolve_email_path(
                    r'e:\Проекты Симрус\Переписка'
                    r'\imap_attachments\INBOX\2\x.pdf')

            self.assertEqual(os.path.normcase(resolved),
                             os.path.normcase(str(target)))

    def test_replace_drive(self):
        self.assertEqual(replace_drive(r'e:\a\b.txt', 'd:'),
                         r'd:\a\b.txt')
        self.assertEqual(replace_drive('e:/a/b.txt', 'd:'),
                         r'd:\a\b.txt')
        self.assertIsNone(replace_drive(r'relative\b.txt', 'd:'))
        self.assertIsNone(replace_drive(r'e:\a\b.txt', 'bad'))

    def test_path_outside_archive_unchanged(self):
        with override_settings(E_MAIL_DIRECTORY=NEW_ROOT):
            self.assertEqual(resolve_email_path(r'C:\temp\x.txt'),
                             r'C:\temp\x.txt')

    def test_model_properties_use_resolved_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'imap_attachments' / 'INBOX' / '1'
            folder.mkdir(parents=True)
            (folder / 'body.html').write_text('<p>hi</p>', encoding='utf-8')

            email = Email.objects.create(
                uid='paths-prop-1',
                subject='Paths',
                category=None,
                link=OLD_ROOT + r'\imap_attachments\INBOX\1',
            )
            att = Attachment.objects.create(
                email=email, filename='f.pdf', size=1,
                file_path=OLD_ROOT + r'\imap_attachments\INBOX\1\f.pdf',
            )
            with override_settings(E_MAIL_DIRECTORY=tmp):
                html_path = email.get_html_file_path()
                file_url = att.file_url

            self.assertTrue(html_path.endswith('body.html'))
            self.assertIn('imap_attachments', html_path)
            self.assertNotIn('e:', html_path.lower())
            self.assertIn('/imap_attachments/INBOX/1/f.pdf', file_url)


class RewriteEmailPathsCommandTest(TestCase):
    def setUp(self):
        self.email = Email.objects.create(
            uid='paths-cmd-1', subject='Paths', category=None,
            link=OLD_ROOT + r'\imap_attachments\INBOX\1')
        self.att = Attachment.objects.create(
            email=self.email, filename='f.pdf', size=1,
            file_path=OLD_ROOT + r'\imap_attachments\INBOX\1\f.pdf')

    def _run(self, *args):
        out = StringIO()
        call_command('rewrite_email_paths', *args, stdout=out)
        return out.getvalue()

    def _refresh(self):
        self.email.refresh_from_db()
        self.att.refresh_from_db()

    def test_dry_run_does_not_change(self):
        out = self._run('--old', OLD_ROOT, '--new', NEW_ROOT)
        self._refresh()
        self.assertTrue(self.email.link.startswith('e:'))
        self.assertTrue(self.att.file_path.startswith('e:'))
        self.assertIn('DRY RUN', out)
        self.assertIn('к замене 1', out)

    def test_apply_rewrites_both_models(self):
        self._run('--old', OLD_ROOT, '--new', NEW_ROOT, '--apply')
        self._refresh()
        self.assertEqual(self.email.link,
                         NEW_ROOT + r'\imap_attachments\INBOX\1')
        self.assertEqual(self.att.file_path,
                         NEW_ROOT + r'\imap_attachments\INBOX\1\f.pdf')

    def test_apply_is_idempotent(self):
        self._run('--old', OLD_ROOT, '--new', NEW_ROOT, '--apply')
        out = self._run('--old', OLD_ROOT, '--new', NEW_ROOT, '--apply')
        self._refresh()
        self.assertEqual(self.email.link,
                         NEW_ROOT + r'\imap_attachments\INBOX\1')
        self.assertIn('к замене 0', out)

    def test_auto_detects_old_root(self):
        with override_settings(E_MAIL_DIRECTORY=NEW_ROOT):
            out = self._run('--apply')
        self._refresh()
        self.assertEqual(self.email.link,
                         NEW_ROOT + r'\imap_attachments\INBOX\1')
        self.assertIn('смена диска', out)

    def test_auto_drive_rename_keeps_markerless_paths(self):
        """Архив 2024-06-26_архив не содержит маркеров — меняется только диск."""
        self.email.link = (
            r'e:\Проекты Симрус\Переписка\2024-06-26_архив\mail')
        self.email.save(update_fields=['link'])
        with override_settings(E_MAIL_DIRECTORY=NEW_ROOT):
            self._run('--apply')
        self._refresh()
        self.assertEqual(
            self.email.link,
            r'd:\Проекты Симрус\Переписка\2024-06-26_архив\mail')

    def test_explicit_drive_rewrite(self):
        self._run('--old', 'e:', '--new', 'd:', '--apply')
        self._refresh()
        self.assertEqual(self.email.link,
                         r'd:\Проекты Симрус\Переписка\Bitrix 24'
                         r'\imap_attachments\INBOX\1')
        self.assertEqual(self.att.file_path,
                         r'd:\Проекты Симрус\Переписка\Bitrix 24'
                         r'\imap_attachments\INBOX\1\f.pdf')

    def test_paths_under_new_root_are_skipped(self):
        self.email.link = NEW_ROOT + r'\imap_attachments\INBOX\2'
        self.email.save(update_fields=['link'])
        out = self._run('--old', OLD_ROOT, '--new', NEW_ROOT, '--apply')
        self._refresh()
        self.assertEqual(self.email.link,
                         NEW_ROOT + r'\imap_attachments\INBOX\2')
        self.assertIn('Email.link: к замене 0', out)
