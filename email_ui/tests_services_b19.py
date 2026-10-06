# -*- coding: utf-8 -*-
"""Блок 19: юниты сервисов email_ui (правила, контакты, треды)."""
from django.contrib.auth.models import User
from django.test import TestCase

from Emails.models import Email
from email_ui.models import Contact, ContactEmail
from email_ui.services.contact_service import ContactService
from email_ui.services.rule_engine import RuleEvaluator
from email_ui.services.thread_service import ThreadService
from StaticData.models import Category, Status


class ServiceFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='b19', password='pw')
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})

    def _email(self, **kw):
        base = {'uid': 'b19-x', 'sender': 'boss@corp.com',
                'subject': 'Смета №5', 'folder': 'inbox'}
        base.update(kw)
        return Email.objects.create(**base)


class RuleEvaluatorTest(ServiceFixtureMixin, TestCase):
    def test_and_logic(self):
        email = self._email()
        conds = [{'field': 'subject', 'operator': 'contains', 'value': 'смета'},
                 {'field': 'sender', 'operator': 'domain', 'value': 'corp.com'}]
        self.assertTrue(RuleEvaluator.evaluate(email, conds))
        conds.append({'field': 'subject', 'operator': 'equals', 'value': 'другое'})
        self.assertFalse(RuleEvaluator.evaluate(email, conds))

    def test_empty_conditions_match_all(self):
        self.assertTrue(RuleEvaluator.evaluate(self._email(), []))

    def test_unknown_condition_blocks(self):
        # Fail-closed: неизвестное условие = правило не срабатывает.
        email = self._email()
        self.assertFalse(RuleEvaluator.evaluate(
            email, [{'field': 'nope', 'operator': 'nope', 'value': 'x'}]))

    def test_regex_condition(self):
        email = self._email(subject='Смета №5 от 01.01')
        self.assertTrue(RuleEvaluator.evaluate(
            email, [{'field': 'subject', 'operator': 'regex',
                     'value': r'№\d+'}]))
        self.assertFalse(RuleEvaluator.evaluate(
            email, [{'field': 'subject', 'operator': 'regex',
                     'value': r'№\d{9}'}]))


class ContactServiceTest(ServiceFixtureMixin, TestCase):
    def test_parse_sender_matrix(self):
        parse = ContactService._parse_sender
        self.assertEqual(parse('Иван <ivan@test.com>'), ('Иван', 'ivan@test.com'))
        self.assertEqual(parse('"Иван" <ivan@test.com>'), ('Иван', 'ivan@test.com'))
        self.assertEqual(parse('ivan@test.com'), (None, 'ivan@test.com'))
        self.assertEqual(parse('Просто Имя'), ('Просто Имя', None))

    def test_extract_creates_and_reuses(self):
        email = self._email(sender='Петров <petr@test.com>')
        c1 = ContactService.extract_from_email(email)
        self.assertEqual(c1.name, 'Петров')
        self.assertTrue(c1.emails.filter(
            email='petr@test.com', is_primary=True).exists())
        c2 = ContactService.extract_from_email(email)
        self.assertEqual(c1.pk, c2.pk)
        self.assertEqual(Contact.objects.filter(
            emails__email='petr@test.com').count(), 1)

    def test_extract_no_sender_none(self):
        email = self._email(sender='')
        self.assertIsNone(ContactService.extract_from_email(email))

    def test_get_or_create_contact(self):
        c1 = ContactService.get_or_create_contact('Имя', 'n@test.com')
        c2 = ContactService.get_or_create_contact('Другое', 'N@TEST.COM')
        self.assertEqual(c1.pk, c2.pk)  # iexact reuse
        self.assertEqual(c2.name, 'Имя')


class ThreadIdTest(ServiceFixtureMixin, TestCase):
    def test_priority_references_first(self):
        email = self._email(references='<a> <b>', in_reply_to='<c>',
                            message_id='<d>')
        self.assertEqual(ThreadService.get_thread_id(email), '<a>')

    def test_fallback_chain(self):
        self.assertEqual(
            ThreadService.get_thread_id(self._email(
                references='', in_reply_to='<c>', message_id='<d>')), '<c>')
        self.assertEqual(
            ThreadService.get_thread_id(self._email(
                references='', in_reply_to='', message_id='<d>')), '<d>')
        self.assertIsNone(ThreadService.get_thread_id(self._email(
            references='', in_reply_to='', message_id='')))
