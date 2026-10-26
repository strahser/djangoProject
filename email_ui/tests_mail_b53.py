# -*- coding: utf-8 -*-
"""Пакет B: шаблоны ответов, фильтр «с Диском», панель просмотра."""
import os
import tempfile

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from Emails.models import Email
from email_ui.models import EmailTemplate, EmailTemplateVariable
from email_ui.services.query_service import filter_emails
from StaticData.models import Category, Status


class ReplyTemplatesTest(TestCase):
    def setUp(self):
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        User.objects.create_user('tuser', 't@t.co', 'pw')
        self.client.login(username='tuser', password='pw')
        self.tpl = EmailTemplate.objects.create(
            name='Принято', subject_template='Re: {{doc}}',
            body_template='<p>Принято, {{name}}.</p>')
        EmailTemplateVariable.objects.create(
            template=self.tpl, name='name', label='Имя', default_value='Иван')

    def test_template_list(self):
        response = self.client.get(reverse('email_ui:template_list'))
        self.assertEqual(response.status_code, 200)
        items = response.json()['templates']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['name'], 'Принято')

    def test_template_render_substitutes_defaults(self):
        response = self.client.get(reverse('email_ui:template_render', args=[self.tpl.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('Иван', data['body'])
        # Незаданная переменная гасится, а не течёт {{doc}} в письмо.
        self.assertNotIn('{{', data['subject'])

    def test_compose_modal_has_templates_dropdown(self):
        response = self.client.get(reverse('email_ui:compose_modal'))
        self.assertContains(response, 'reply-templates-list')
        self.assertContains(response, 'insertReplyTemplate')


class DiskLinksFilterTest(TestCase):
    def setUp(self):
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        User.objects.create_user('duser', 'd@t.co', 'pw')
        self.client.login(username='duser', password='pw')
        from email_ui.utils import DISK_LINKS_FILENAME
        self.tmp_with = tempfile.mkdtemp()
        with open(os.path.join(self.tmp_with, 'body.html'), 'w', encoding='utf-8') as f:
            f.write('<div>Тело</div>')
        with open(os.path.join(self.tmp_with, DISK_LINKS_FILENAME), 'w', encoding='utf-8') as f:
            f.write('<a href="https://disk.yandex.ru/x">Файл</a>')
        self.tmp_without = tempfile.mkdtemp()
        with open(os.path.join(self.tmp_without, 'body.html'), 'w', encoding='utf-8') as f:
            f.write('<div>Тело</div>')
        self.m_with = Email.objects.create(
            uid='b-disk-1', email_type='IN', subject='С диском',
            sender='a@t.co', folder='inbox', sent_status='sent',
            link=self.tmp_with)
        self.m_without = Email.objects.create(
            uid='b-disk-2', email_type='IN', subject='Без диска',
            sender='a@t.co', folder='inbox', sent_status='sent',
            link=self.tmp_without)

    def test_scan_command_dry_run_by_default(self):
        call_command('scan_disk_links')
        self.m_with.refresh_from_db()
        self.assertFalse(self.m_with.has_disk_links)

    def test_scan_command_apply(self):
        call_command('scan_disk_links', apply=True)
        self.m_with.refresh_from_db()
        self.m_without.refresh_from_db()
        self.assertTrue(self.m_with.has_disk_links)
        self.assertFalse(self.m_without.has_disk_links)

    def test_filter_has_disk_links(self):
        self.m_with.has_disk_links = True
        self.m_with.save(update_fields=['has_disk_links'])
        pks = set(filter_emails(
            Email.objects.filter(folder='inbox'),
            {'folder': 'inbox', 'has_disk_links': True},
        ).values_list('pk', flat=True))
        self.assertIn(self.m_with.pk, pks)
        self.assertNotIn(self.m_without.pk, pks)

    def test_email_body_self_heals_flag(self):
        self.assertFalse(self.m_with.has_disk_links)
        response = self.client.get(reverse('email_ui:email_body', args=[self.m_with.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('letter-disk', response.content.decode('utf-8', 'replace'))
        self.m_with.refresh_from_db()
        self.assertTrue(self.m_with.has_disk_links)


class PreviewPaneTest(TestCase):
    def setUp(self):
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        User.objects.create_user('puser', 'p@t.co', 'pw')
        self.client.login(username='puser', password='pw')
        Email.objects.create(
            uid='b-prev-1', email_type='IN', subject='Тема',
            sender='a@t.co', folder='inbox', sent_status='sent')

    def test_inbox_has_preview_toggle_and_pane(self):
        response = self.client.get(reverse('email_ui:inbox', args=['inbox']))
        self.assertContains(response, 'preview-toggle-btn')
        self.assertContains(response, 'preview-pane')
        self.assertContains(response, 'EmailPreview')

    def test_rows_carry_email_id(self):
        response = self.client.get(
            reverse('email_ui:email_list_partial'), {'folder': 'inbox'})
        self.assertContains(response, 'data-email-id')
