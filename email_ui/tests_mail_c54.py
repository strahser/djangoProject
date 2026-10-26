# -*- coding: utf-8 -*-
"""Пакет C: закреплённые фильтры, применение по GET, клавиши (JSON/POST)."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from Emails.models import Email
from email_ui.models import SavedFilter
from StaticData.models import Category, Status


class PinnedFiltersTest(TestCase):
    def setUp(self):
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        self.user = User.objects.create_user('cuser', 'c@t.co', 'pw')
        self.other = User.objects.create_user('cother', 'o@t.co', 'pw')
        self.client.login(username='cuser', password='pw')
        self.sf = SavedFilter.objects.create(
            name='Важные', user=self.user,
            filters={'is_important': ['1']}, folder='inbox')

    def test_pin_defaults_off(self):
        self.assertFalse(self.sf.is_pinned)

    def test_toggle_pin(self):
        response = self.client.post(reverse('email_ui:toggle_pin_filter', args=[self.sf.pk]))
        self.assertEqual(response.status_code, 200)
        self.sf.refresh_from_db()
        self.assertTrue(self.sf.is_pinned)
        self.client.post(reverse('email_ui:toggle_pin_filter', args=[self.sf.pk]))
        self.sf.refresh_from_db()
        self.assertFalse(self.sf.is_pinned)

    def test_toggle_pin_foreign_forbidden(self):
        self.client.login(username='cother', password='pw')
        response = self.client.post(reverse('email_ui:toggle_pin_filter', args=[self.sf.pk]))
        self.assertEqual(response.status_code, 404)

    def test_apply_via_get(self):
        response = self.client.get(reverse('email_ui:apply_saved_filter', args=[self.sf.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('is_important=1', response['Location'])

    def test_apply_shared_by_other_user(self):
        self.sf.is_shared = True
        self.sf.save(update_fields=['is_shared'])
        self.client.login(username='cother', password='pw')
        response = self.client.get(reverse('email_ui:apply_saved_filter', args=[self.sf.pk]))
        self.assertEqual(response.status_code, 302)

    def test_sidebar_shows_pinned(self):
        self.sf.is_pinned = True
        self.sf.save(update_fields=['is_pinned'])
        response = self.client.get(reverse('email_ui:inbox', args=['inbox']))
        self.assertContains(response, 'Сохранённые')
        self.assertContains(response, 'Важные')

    def test_save_modal_and_save_with_params(self):
        response = self.client.get(
            reverse('email_ui:save_filter_modal'),
            {'folder': 'inbox', 'filter_params': 'is_unread=1&folder=inbox'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'filter_params')
        response = self.client.post(
            reverse('email_ui:save_current_filter'),
            {'name': 'Непрочитанные', 'folder': 'inbox',
             'filter_params': 'is_unread=1&folder=inbox'})
        self.assertEqual(response.status_code, 204)
        saved = SavedFilter.objects.get(name='Непрочитанные')
        self.assertEqual(saved.filters.get('is_unread'), ['1'])

    def test_manager_modal_renders(self):
        response = self.client.get(reverse('email_ui:saved_filters_modal'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Важные')


class KeyboardEndpointsTest(TestCase):
    def setUp(self):
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        User.objects.create_user('kuser', 'k@t.co', 'pw')
        self.client.login(username='kuser', password='pw')
        self.mail = Email.objects.create(
            uid='c-key-1', email_type='IN', subject='Тема',
            sender='a@t.co', folder='inbox', sent_status='sent')

    def test_toggle_important_json_for_fetch(self):
        response = self.client.post(
            reverse('email_ui:toggle_important', args=[self.mail.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_important'])
        self.mail.refresh_from_db()
        self.assertTrue(self.mail.is_important)

    def test_bulk_single_archive(self):
        response = self.client.post(
            reverse('email_ui:bulk_action'),
            {'selected_emails': [str(self.mail.pk)], 'action': 'move',
             'move_to': 'archive', 'folder': 'inbox'})
        self.mail.refresh_from_db()
        self.assertEqual(self.mail.folder, 'archive')

    def test_bulk_single_unread(self):
        self.mail.is_read = True
        self.mail.save(update_fields=['is_read'])
        self.client.post(
            reverse('email_ui:bulk_action'),
            {'selected_emails': [str(self.mail.pk)], 'action': 'mark_unread',
             'folder': 'inbox'})
        self.mail.refresh_from_db()
        self.assertFalse(self.mail.is_read)
