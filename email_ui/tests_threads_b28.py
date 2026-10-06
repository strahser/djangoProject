"""Блок 28 (B2): гарды thread-хелперов до переезда в services/thread_service.

Пины факта: direction in/out, группировка по норме темы, сортировка
по свежим, добор связанных из inbox+sent, включение выбранных из любых
папок, пустой вход -> [].
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from Emails.models import Email
from email_ui.views import (
    _attach_thread_context,
    _attach_thread_page_heads,
    _build_selection_threads,
    _build_thread_list,
)


class AttachContextTest(TestCase):
    def test_direction_without_files(self):
        inn = Email(email_type='IN', subject='S')
        out = Email(email_type='OUT', subject='S')
        _attach_thread_context([inn, out], with_head=False)
        self.assertEqual(
            (inn.direction, inn.direction_label), ('in', 'Входящее'))
        self.assertEqual(
            (out.direction, out.direction_label), ('out', 'Исходящее'))

    def test_head_defaults_to_empty_without_files(self):
        mail = Email(email_type='IN', subject='S')
        _attach_thread_context([mail], with_head=True)
        self.assertEqual(mail.body_head, '')


class BuildThreadListTest(TestCase):
    def setUp(self):
        from StaticData.models import Category, Status
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        self._mk('Re: Привет', 5, 'IN')
        self._mk('Привет', 60, 'OUT')
        self._mk('Другое', 10, 'IN')

    def _mk(self, subject, minutes_ago, kind='IN'):
        return Email.objects.create(
            uid=f'b28-{minutes_ago}-{kind}',
            subject=subject, sender='a@t.co', email_type=kind,
            folder='inbox', sent_status='sent',
            email_stamp=timezone.now() - timedelta(minutes=minutes_ago))

    def test_groups_by_normalized_subject_latest_first(self):
        mails = list(Email.objects.all())
        threads = _build_thread_list(mails)
        self.assertEqual(len(threads), 2)
        # Свежая цепочка первая, тема — из самого свежего (с Re:).
        self.assertEqual(threads[0]['subject'], 'Re: Привет')
        self.assertEqual(threads[0]['count'], 2)
        self.assertEqual(threads[0]['in_count'], 1)
        self.assertEqual(threads[0]['out_count'], 1)


class SelectionThreadsTest(TestCase):
    def setUp(self):
        from StaticData.models import Category, Status
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        now = timezone.now()
        self.sel = Email.objects.create(
            uid='b28-sel', subject='Re: Вопрос', sender='a@t.co',
            email_type='IN', folder='trash', sent_status='sent',
            thread_id='T-1', email_stamp=now)
        self.mate = Email.objects.create(
            uid='b28-mate', subject='Вопрос', sender='b@t.co',
            email_type='OUT', folder='sent', sent_status='sent',
            thread_id='T-1', email_stamp=now - timedelta(minutes=30))
        self.stranger = Email.objects.create(
            uid='b28-str', subject='Постороннее', sender='c@t.co',
            email_type='IN', folder='inbox', sent_status='sent',
            email_stamp=now - timedelta(minutes=10))

    def test_empty_ids_empty_out(self):
        self.assertEqual(_build_selection_threads([]), [])

    def test_selected_included_from_any_folder_plus_mates(self):
        threads = _build_selection_threads([self.sel.pk])
        pks = {e.pk for t in threads for e in t['emails']}
        self.assertIn(self.sel.pk, pks)
        self.assertIn(self.mate.pk, pks)
        self.assertNotIn(self.stranger.pk, pks)

    def test_page_heads_hook_runs(self):
        threads = _build_selection_threads([self.sel.pk])
        _attach_thread_page_heads(threads)
        for t in threads:
            for e in t['emails']:
                self.assertTrue(hasattr(e, 'body_head'))
