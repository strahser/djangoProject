# -*- coding: utf-8 -*-
"""Тесты: тихая обработка ошибок входа IMAP и флаг автозагрузки почты.

Яндекс периодически отвечает «[UNAVAILABLE] LOGIN internal server error»
— это его временная внутренняя ошибка, а не ошибка нашего кода. Раньше она
падала в общий except и печаталась полным traceback прямо при старте
сервера. Теперь:
  * UNAVAILABLE -> повтор входа (с паузой) и короткое сообщение;
  * отказ по учётным данным -> без повторов, с подсказкой;
  * и то, и другое -> warning без traceback.
"""
from unittest import mock

from django.test import SimpleTestCase

from imap_tools.errors import MailboxLoginError

from Emails.ЕmailParser.ParsingImapEmailToDB import ParsingImapEmailToDB


def _login_error(text: str) -> MailboxLoginError:
    return MailboxLoginError(("NO", [text.encode('utf-8')]), "OK")


class TransientLoginErrorTest(SimpleTestCase):
    """Разбор ошибок входа IMAP."""

    def test_unavailable_is_transient(self):
        exc = _login_error('[UNAVAILABLE] LOGIN internal server error')
        self.assertTrue(ParsingImapEmailToDB._is_transient_login_error(exc))

    def test_auth_failure_is_not_transient(self):
        exc = _login_error('AUTHENTICATIONFAILED Invalid credentials')
        self.assertFalse(ParsingImapEmailToDB._is_transient_login_error(exc))

    def test_retry_on_transient_error(self):
        """Временная ошибка сервера -> повтор входа."""
        parser = ParsingImapEmailToDB(root_folder_path='.')
        error = _login_error('[UNAVAILABLE] LOGIN internal server error')
        with mock.patch.object(parser, '_login',
                               side_effect=[error, error, 'MAILBOX']), \
                mock.patch('Emails.ЕmailParser.ParsingImapEmailToDB.time.sleep'):
            self.assertEqual(parser._login_with_retry('INBOX'), 'MAILBOX')

    def test_no_retry_on_bad_credentials(self):
        """Неверный пароль -> сразу исключение, без бесполезных повторов."""
        parser = ParsingImapEmailToDB(root_folder_path='.')
        error = _login_error('AUTHENTICATIONFAILED Invalid credentials')
        with mock.patch.object(parser, '_login', side_effect=error) as login, \
                mock.patch('Emails.ЕmailParser.ParsingImapEmailToDB.time.sleep'):
            with self.assertRaises(MailboxLoginError):
                parser._login_with_retry('INBOX')
            self.assertEqual(login.call_count, 1)

    def test_main_login_error_without_traceback(self):
        """Ошибка входа логируется коротко (без logger.exception)."""
        parser = ParsingImapEmailToDB(root_folder_path='.')
        error = _login_error('[UNAVAILABLE] LOGIN internal server error')
        with mock.patch.object(parser, '_get_existing_uids', return_value=set()), \
                mock.patch.object(parser, '_login_with_retry', side_effect=error), \
                mock.patch('Emails.ЕmailParser.ParsingImapEmailToDB.logger') as log:
            parser.main('IN', 'INBOX', limit=1)
            self.assertTrue(log.warning.called)
            self.assertFalse(log.exception.called)
        self.assertTrue(any('IMAP login' in e for e in parser.error_list))


class AutoFetchFlagTest(SimpleTestCase):
    """Флаг EMAIL_AUTO_FETCH_ENABLED."""

    def test_disabled_scheduler_does_not_start(self):
        from django.test import override_settings
        from email_ui import scheduled

        with override_settings(EMAIL_AUTO_FETCH_ENABLED=False), \
                mock.patch.object(scheduled, 'BackgroundScheduler') as scheduler:
            scheduled._SCHEDULER_STARTED = False
            scheduled.start_email_fetch_scheduler()
            self.assertFalse(scheduler.called)
        scheduled._SCHEDULER_STARTED = False

    def test_enabled_scheduler_starts(self):
        from django.test import override_settings
        from email_ui import scheduled

        with override_settings(EMAIL_AUTO_FETCH_ENABLED=True), \
                mock.patch.object(scheduled, 'BackgroundScheduler') as scheduler:
            scheduled._SCHEDULER_STARTED = False
            scheduled.start_email_fetch_scheduler()
            self.assertTrue(scheduler.called)
        scheduled._SCHEDULER_STARTED = False
