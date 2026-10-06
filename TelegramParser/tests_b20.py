# -*- coding: utf-8 -*-
"""Блок 20: гарды TelegramParser (экстракторы, важность, auth вьюх)."""
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from TelegramParser.importance import calculate_importance
from TelegramParser.models import TelegramChannel
from TelegramParser.parser import extract_links_from_entities, extract_tags_from_entities


def _msg(text, entities=None):
    return SimpleNamespace(message=text, entities=entities or [])


class ExtractorTest(TestCase):
    def test_tags_regex_fallback(self):
        self.assertEqual(
            extract_tags_from_entities(_msg('Пост #важно и #срочно')),
            ['важно', 'срочно'])

    def test_tags_none_message(self):
        self.assertEqual(extract_tags_from_entities(_msg(None)), [])

    def test_tags_entity_slice(self):
        # offset указывает на '#', length включает его (как у telethon).
        ent = SimpleNamespace(hashtag=True, offset=5, length=6)
        self.assertEqual(
            extract_tags_from_entities(_msg('Пост #важно', [ent])), ['важно'])

    def test_links_entity_and_fallback(self):
        ent = SimpleNamespace(url='https://x.ru/a')
        self.assertEqual(
            extract_links_from_entities(_msg('см сюда', [ent])), ['https://x.ru/a'])
        self.assertEqual(
            extract_links_from_entities(_msg('идти на https://y.ru/b')),
            ['https://y.ru/b'])
        self.assertEqual(extract_links_from_entities(_msg('без ссылок')), [])

    def test_links_skip_bare_hashtag_entity(self):
        ent = SimpleNamespace(hashtag=True)
        self.assertEqual(
            extract_links_from_entities(_msg('пост #тэг', [ent])), [])


class ImportanceTest(TestCase):
    def test_matrix(self):
        calc = calculate_importance
        self.assertEqual(calc(0, [], []), 1)
        self.assertEqual(calc(5, [], []), 2)
        self.assertEqual(calc(20, [], []), 2)
        self.assertEqual(calc(50, [], []), 3)
        self.assertEqual(calc(0, ['Important'], []), 2)
        self.assertEqual(calc(0, [], ['https://github.com/x']), 2)
        self.assertEqual(calc(50, ['Important'], ['https://github.com/x']), 4)


class ParserViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='b20', password='pw')
        cls.channel = TelegramChannel.objects.create(
            name='Канал', username='chan')

    def test_anonymous_redirects(self):
        self.assertEqual(
            self.client.get(reverse('TelegramParser:parse_status')).status_code, 302)
        self.assertEqual(
            self.client.get(reverse('TelegramParser:fetch_channel_data',
                                    args=[self.channel.pk])).status_code, 302)

    def test_bad_channel_404(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(reverse('TelegramParser:fetch_channel_data',
                                    args=[999999])).status_code, 404)

    def test_fetch_starts_thread_and_redirects(self):
        from unittest.mock import patch
        self.client.force_login(self.user)
        with patch('TelegramParser.views._run_parse_in_thread') as mock_run:
            resp = self.client.get(reverse(
                'TelegramParser:fetch_channel_data', args=[self.channel.pk]))
        self.assertEqual(resp.status_code, 302)
        mock_run.assert_called_once()
        # Без referer — fallback на changelist каналов (был 500).
        self.assertIn('/admin/TelegramParser/telegramchannel/',
                      resp.get('Location'))

    def test_status_shape(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('TelegramParser:parse_status'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('logs', resp.json())
