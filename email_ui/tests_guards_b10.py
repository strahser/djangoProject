# -*- coding: utf-8 -*-
"""Блок 10: гарды справочников email_ui (поиск контактов, теги, группы)."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from Emails.models import Email
from email_ui.models import (
    Contact,
    ContactEmail,
    ContactGroup,
    EmailEmailTag,
    EmailTag,
)
from StaticData.models import Category, Status


class DirectoryFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='b10_user', password='pw')
        # FK-дефолты Emails_email (category_id=1).
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})

    def setUp(self):
        self.client.force_login(self.user)

    def _contact(self, name, *emails, primary=0):
        c = Contact.objects.create(name=name)
        for i, addr in enumerate(emails):
            ContactEmail.objects.create(
                contact=c, email=addr, is_primary=(i == primary))
        return c


class ContactSearchGuardsTest(DirectoryFixtureMixin, TestCase):
    def test_finds_by_name_and_email(self):
        # SQLite LIKE регистронезависим только для ASCII — латиница.
        self._contact('Ivan Petrov', 'ivan@test.com')
        self._contact('Sidorov', 'sid@test.com')
        resp = self.client.get(reverse('email_ui:contact_search'), {'q': 'ivan'})
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            set(rows[0].keys()), {'id', 'name', 'email', 'company'})

    def test_primary_email_preferred(self):
        self._contact('Multi', 'second@test.com', 'first@test.com', primary=1)
        resp = self.client.get(reverse('email_ui:contact_search'), {'q': 'multi'})
        self.assertEqual(resp.json()[0]['email'], 'first@test.com')

    def test_query_count(self):
        # Блок 10: сам поиск — 2 запроса (контакты + emails одним prefetch);
        # плюс сессия и юзер тестового клиента. Было ~3 на строку.
        for i in range(3):
            self._contact(f'Contact {i}', f'c{i}@test.com', f'x{i}@test.com')
        with self.assertNumQueries(4):
            resp = self.client.get(reverse('email_ui:contact_search'), {'q': 'contact'})
        self.assertEqual(len(resp.json()), 3)


class BulkAssignTagTest(DirectoryFixtureMixin, TestCase):
    def test_assign_many_and_idempotent(self):
        tag = EmailTag.objects.create(name='срочно')
        ids = [Email.objects.create(
            uid=f'b10-{i}', sender='s@t.com', folder='inbox').pk
            for i in range(3)]
        url = reverse('email_ui:bulk_assign_tag')
        resp = self.client.post(url, {'email_ids': [str(i) for i in ids],
                                      'tag_id': str(tag.pk)})
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(EmailEmailTag.objects.filter(tag=tag).count(), 3)
        # Повтор — без дублей (unique_together), снова 204.
        resp2 = self.client.post(url, {'email_ids': [str(ids[0])],
                                       'tag_id': str(tag.pk)})
        self.assertEqual(resp2.status_code, 204)
        self.assertEqual(EmailEmailTag.objects.filter(tag=tag).count(), 3)

    def test_missing_args_400(self):
        resp = self.client.post(reverse('email_ui:bulk_assign_tag'), {})
        self.assertEqual(resp.status_code, 400)


class AssignTagTest(DirectoryFixtureMixin, TestCase):
    def test_create_by_name_and_reuse(self):
        email = Email.objects.create(
            uid='b10-one', sender='s@t.com', folder='inbox')
        url = reverse('email_ui:assign_tag')
        resp = self.client.post(url, {'email_id': str(email.pk),
                                      'tag_name': 'новый'})
        self.assertEqual(resp.json(), {'success': True, 'created': True,
                                       'tag_name': 'новый',
                                       'tag_color': resp.json()['tag_color']})
        resp2 = self.client.post(url, {'email_id': str(email.pk),
                                       'tag_name': 'новый'})
        self.assertFalse(resp2.json()['created'])
        self.assertEqual(EmailTag.objects.filter(name='новый').count(), 1)

    def test_missing_tag_400(self):
        email = Email.objects.create(
            uid='b10-two', sender='s@t.com', folder='inbox')
        resp = self.client.post(reverse('email_ui:assign_tag'),
                                {'email_id': str(email.pk)})
        self.assertEqual(resp.status_code, 400)

    def test_garbage_email_id_400(self):
        # Блок 10: мусор в email_id — 400, а не 500 от sanitize_id.
        resp = self.client.post(reverse('email_ui:assign_tag'),
                                {'email_id': 'мусор', 'tag_name': 'x'})
        self.assertEqual(resp.status_code, 400)


class GroupCycleTest(DirectoryFixtureMixin, TestCase):
    def test_cycle_rejected(self):
        g1 = ContactGroup.objects.create(name='G1')
        g2 = ContactGroup.objects.create(name='G2')
        g1.subgroups.add(g2)
        resp = self.client.post(
            reverse('email_ui:group_add_subgroup', args=[g2.pk]),
            {'subgroup_id': str(g1.pk)}, follow=True)
        self.assertEqual(resp.status_code, 200)
        msgs = [str(m) for m in resp.context['messages']]
        self.assertTrue(any('цикл' in m for m in msgs))
        self.assertNotIn(g1, g2.subgroups.all())

    def test_add_contact_roundtrip(self):
        g = ContactGroup.objects.create(name='G')
        c = self._contact('Участник', 'm@test.com')
        resp = self.client.post(
            reverse('email_ui:group_add_contact', args=[g.pk]),
            {'contact_id': str(c.pk)})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(c, g.contacts.all())
        resp = self.client.post(
            reverse('email_ui:group_remove_contact', args=[g.pk]),
            {'contact_id': str(c.pk)})
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn(c, g.contacts.all())
