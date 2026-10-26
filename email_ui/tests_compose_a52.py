"""Пакет A удобство почты: фразы/минус в поиске, имя вложения, цитата, автосейв."""
import os
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from Emails.models import Attachment, Email
from email_ui.services.query_service import (
    _search_tokens, filter_emails, highlight_words,
)
from email_ui.utils import quote_body_html
from StaticData.models import Category, Status


class SearchTokensTest(TestCase):
    def test_phrase_is_single_token(self):
        toks = _search_tokens('"совещание К-1" итоги')
        self.assertIn(('совещание К-1', False, False), toks)
        self.assertIn(('итоги', False, False), toks)
        self.assertEqual(len(toks), 2)

    def test_minus_marks_exclude(self):
        toks = _search_tokens('смета -корректировка')
        self.assertIn(('смета', False, False), toks)
        self.assertIn(('корректировка', False, True), toks)

    def test_minus_phrase(self):
        toks = _search_tokens('-"точный текст"')
        self.assertEqual(toks, [('точный текст', False, True)])

    def test_minus_address(self):
        toks = _search_tokens('-spam@x.ru')
        self.assertEqual(toks, [('spam@x.ru', True, True)])

    def test_plain_words_unchanged(self):
        toks = _search_tokens('Аркадий Кунаев')
        self.assertEqual(toks, [('Аркадий', False, False), ('Кунаев', False, False)])

    def test_empty(self):
        self.assertEqual(_search_tokens(''), [])
        self.assertEqual(_search_tokens(None), [])


class SearchFilterTest(TestCase):
    def setUp(self):
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        self.m1 = Email.objects.create(
            uid='a-phrase-1', subject='Совещание К-1 итоги', sender='a@t.co',
            email_type='IN', folder='inbox', sent_status='sent')
        self.m2 = Email.objects.create(
            uid='a-phrase-2', subject='Совещание итоги без корпуса', sender='b@t.co',
            email_type='IN', folder='inbox', sent_status='sent')
        self.m3 = Email.objects.create(
            uid='a-phrase-3', subject='Смета корректировка', sender='c@t.co',
            email_type='IN', folder='inbox', sent_status='sent')

    def _pks(self, **params):
        params.setdefault('folder', 'inbox')
        return set(filter_emails(
            Email.objects.filter(folder='inbox'), params
        ).values_list('pk', flat=True))

    def test_phrase_matches_exact_order(self):
        pks = self._pks(search='"Совещание К-1"')
        self.assertIn(self.m1.pk, pks)
        self.assertNotIn(self.m2.pk, pks)

    def test_minus_excludes(self):
        pks = self._pks(search='Совещание -без')
        self.assertIn(self.m1.pk, pks)
        self.assertNotIn(self.m2.pk, pks)
        pks2 = self._pks(search='Совещание -итоги')
        self.assertNotIn(self.m1.pk, pks2)
        self.assertNotIn(self.m2.pk, pks2)
        # Без минуса находится — исключает именно минус.
        self.assertIn(self.m3.pk, self._pks(search='Смета'))
        self.assertNotIn(self.m3.pk, self._pks(search='Смета -корректировка'))

    def test_attachment_name(self):
        Attachment.objects.create(
            email=self.m3, filename='смета_Изм5.pdf',
            file_path='/tmp/x.pdf', size=1, content_type='application/pdf')
        pks = self._pks(attachment_name='Изм5')
        self.assertEqual(pks, {self.m3.pk})

    def test_attachment_name_multi_or(self):
        Attachment.objects.create(
            email=self.m1, filename='протокол.docx',
            file_path='/tmp/p.docx', size=1,
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        Attachment.objects.create(
            email=self.m3, filename='смета.pdf',
            file_path='/tmp/s.pdf', size=1, content_type='application/pdf')
        pks = self._pks(attachment_name='протокол, смета')
        self.assertEqual(pks, {self.m1.pk, self.m3.pk})

    def test_highlight_words_skips_negations(self):
        words = highlight_words('"Совещание К-1" -без')
        self.assertIn('Совещание', words)
        self.assertIn('К-1', words)
        self.assertNotIn('без', words)


class QuoteBodyTest(TestCase):
    def test_quote_drops_headers_quotes_signature(self):
        html = (
            '<div>Отправитель:boss@x.ru</div>'
            '<div>Добрый день, высылаю Изм 5.</div>'
            '<blockquote><p>Старая переписка</p></blockquote>'
            '<div>-- </div><div>С уважением, Босс</div>'
        )
        out = quote_body_html(html)
        self.assertIn('Добрый день', out)
        self.assertNotIn('Старая переписка', out)
        self.assertNotIn('Отправитель:', out)
        self.assertNotIn('С уважением', out)

    def test_quote_truncates_long(self):
        html = '<div>' + '</div><div>'.join(f'Абзац номер {i} текста' for i in range(100)) + '</div>'
        out = quote_body_html(html, limit=500)
        self.assertIn('цитата сокращена', out)
        self.assertLess(len(out), len(html))

    def test_quote_empty(self):
        self.assertEqual(quote_body_html(''), '')


class ReplyQuoteViewTest(TestCase):
    def setUp(self):
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        User.objects.create_user('quser', 'q@t.co', 'pw')
        self.client.login(username='quser', password='pw')
        self.tmp_dir = tempfile.mkdtemp()
        with open(os.path.join(self.tmp_dir, 'body.html'), 'w', encoding='utf-8') as f:
            f.write(
                '<div>Добрый день, смета во вложении.</div>'
                '<script>alert("xss")</script>'
                '<blockquote><p>Старый тред</p></blockquote>'
                '<div>-- </div><div>Подпись</div>')
        self.mail = Email.objects.create(
            uid='a-quote-1', subject='Смета', sender='boss@x.ru',
            email_type='IN', folder='inbox', sent_status='sent',
            link=self.tmp_dir)

    def test_reply_quote_cleaned_and_trimmed(self):
        response = self.client.get(reverse('email_ui:reply_modal', args=[self.mail.pk, 'reply']))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8', 'replace')
        self.assertIn('Добрый день', html)
        self.assertIn('писал:', html)
        # Скрипт исходника не должен попасть даже в экранированном виде.
        self.assertNotIn('alert(', html)
        self.assertNotIn('Старый тред', html)
        self.assertNotIn('Подпись', html)


class AutosaveDraftTest(TestCase):
    def setUp(self):
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        User.objects.create_user('asuser', 'as@t.co', 'pw')
        self.client.login(username='asuser', password='pw')

    def test_autosave_creates_and_returns_id(self):
        with self.settings(DRAFT_DIRECTORY=os.path.join(tempfile.gettempdir(), 'test_autosave')):
            response = self.client.post(reverse('email_ui:autosave_draft'), {
                'to': 'a@t.co', 'subject': 'Черновик', 'body': '<p>текст</p>'})
        self.assertEqual(response.status_code, 200)
        draft_id = response.json()['id']
        self.assertIsNotNone(draft_id)
        draft = Email.objects.get(pk=draft_id)
        self.assertEqual(draft.folder, 'drafts')
        self.assertEqual(draft.subject, 'Черновик')

    def test_autosave_updates_same_draft(self):
        with self.settings(DRAFT_DIRECTORY=os.path.join(tempfile.gettempdir(), 'test_autosave')):
            r1 = self.client.post(reverse('email_ui:autosave_draft'), {
                'subject': 'V1', 'body': 'one'})
            draft_id = r1.json()['id']
            r2 = self.client.post(reverse('email_ui:autosave_draft'), {
                'draft_id': draft_id, 'subject': 'V2', 'body': 'two'})
        self.assertEqual(r2.json()['id'], draft_id)
        self.assertEqual(Email.objects.filter(folder='drafts').count(), 1)
        self.assertEqual(Email.objects.get(pk=draft_id).subject, 'V2')

    def test_autosave_skips_empty(self):
        response = self.client.post(reverse('email_ui:autosave_draft'), {
            'to': '', 'subject': '', 'body': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['id'])
        self.assertEqual(Email.objects.filter(folder='drafts').count(), 0)


class HlFilterTest(TestCase):
    def test_hl_marks_and_escapes(self):
        from email_ui.templatetags.email_filters import hl
        out = str(hl('Смета <b>Изм5</b>', ['смета', 'Изм5']))
        self.assertIn('<mark>', out)
        self.assertIn('&lt;b&gt;', out)
        self.assertNotIn('<b>Изм5</b>', out)

    def test_hl_empty_words_returns_value(self):
        from email_ui.templatetags.email_filters import hl
        self.assertEqual(hl('Текст', []), 'Текст')
