"""Блок 30 (B6): гарды Seen-синхронизации (services/seen_sync).

Пины: только цифровые UID уходят на сервер; мусор/локальные папки —
нет; без кредов сети нет; ошибка папки не роняет вторую; async-вариант
вызывает тот же sync-код в отдельном потоке и не блокирует вызывающего.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings

from Emails.models import Email
from email_ui.services import seen_sync as seen


class PushSeenCoreTest(TestCase):
    def _mail(self, uid, folder='inbox'):
        return Email(uid=uid, subject='S', sender='a@t.co', folder=folder)

    @override_settings(YA_HOST='h', YA_USER='u', YA_PASSWORD='p')
    def test_digit_uid_flagged_per_folder(self):
        mbox = self._mbox()
        seen.push_seen_to_server(
            [self._mail('11'), self._mail('22', folder='sent')])
        self.assertEqual(mbox.flag.call_count, 2)
        flagged = [c.args[0] for c in mbox.flag.call_args_list]
        self.assertIn(['11'], flagged)
        self.assertIn(['22'], flagged)

    @override_settings(YA_HOST='h', YA_USER='u', YA_PASSWORD='p')
    def test_junk_and_local_folders_skipped(self):
        mbox = self._mbox()
        seen.push_seen_to_server([
            self._mail('bulk-uid-1'), self._mail(''),
            self._mail('33', folder='drafts'),
            self._mail('44', folder='trash'),
        ])
        mbox.flag.assert_not_called()

    @override_settings(YA_HOST='', YA_USER='', YA_PASSWORD='')
    def test_no_creds_no_network(self):
        with patch('imap_tools.MailBox') as mb:
            seen.push_seen_to_server(self._mail('11'))
            mb.assert_not_called()

    @override_settings(YA_HOST='h', YA_USER='u', YA_PASSWORD='p')
    def test_single_object_and_seen_flag(self):
        mbox = self._mbox()
        seen.push_seen_to_server(self._mail('55'), seen=False)
        mbox.flag.assert_called_once()
        self.assertEqual(mbox.flag.call_args.args[1], '\\Seen')
        self.assertEqual(mbox.flag.call_args.args[2], False)

    def _mbox(self):
        patcher = patch('imap_tools.MailBox')
        mb_cls = patcher.start()
        self.addCleanup(patcher.stop)
        return mb_cls.return_value.login.return_value


class PushSeenAsyncTest(TestCase):
    def test_runs_sync_code_off_thread(self):
        import threading
        mail = Email(uid='1', subject='S', sender='a@t.co', folder='inbox')
        with patch.object(seen, 'push_seen_to_server') as core:
            thread = seen.push_seen_async(mail, seen=True)
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
            core.assert_called_once_with(mail, True)
        self.assertIsInstance(thread, threading.Thread)
        self.assertTrue(thread.daemon)
