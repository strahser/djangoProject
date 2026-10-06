"""Блок 30 (B8): гард на JOIN-фан-аут комбинации tags+has_attachments.

filter_emails ставит distinct() на каждую ветку отдельно; комбинация двух
M2M/reverse-FK JOIN'ов не должна дублировать строки (2 тега x 2 вложения).
Пин факта: письмо встречается ровно один раз.
"""
from django.test import TestCase

from Emails.models import Attachment, Email
from email_ui.models import EmailEmailTag, EmailTag
from email_ui.services.query_service import filter_emails
from StaticData.models import Category, Status


class FilterFanoutTest(TestCase):
    def setUp(self):
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        self.mail = Email.objects.create(
            uid='b30-fan', subject='S', sender='a@t.co',
            email_type='IN', folder='inbox', sent_status='sent')
        self.t1 = EmailTag.objects.create(name='T1-б30', color='#ff0000')
        self.t2 = EmailTag.objects.create(name='T2-б30', color='#00ff00')
        EmailEmailTag.objects.create(email=self.mail, tag=self.t1)
        EmailEmailTag.objects.create(email=self.mail, tag=self.t2)
        for i in range(2):
            Attachment.objects.create(
                email=self.mail, filename=f'f{i}.txt',
                file_path=f'/tmp/f{i}.txt', size=1,
                content_type='text/plain')

    def _pks(self, **params):
        params.setdefault('folder', 'inbox')
        return list(filter_emails(
            Email.objects.filter(folder='inbox'), params
        ).values_list('pk', flat=True))

    def test_tags_and_attachments_no_duplicates(self):
        pks = self._pks(tags=[self.t1.pk, self.t2.pk], has_attachments=True)
        self.assertEqual(pks.count(self.mail.pk), 1)

    def test_multi_tags_no_duplicates(self):
        pks = self._pks(tags=[self.t1.pk, self.t2.pk])
        self.assertEqual(pks.count(self.mail.pk), 1)
