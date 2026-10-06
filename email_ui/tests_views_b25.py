"""Блок 25: гарды чистых хелперов email_ui/views.py до выноса в services.

Принцип: тесты описывают ФАКТ, не идеал (включая quirks — с пометкой).
После выноса в email_ui/services/query_service.py + navigation.py
эти же тесты должны остаться зелёными без правок (views re-export).
"""
from django.contrib.auth.models import User
from django.db.models import Q
from django.test import RequestFactory, TestCase
from django.urls import reverse

from Emails.models import Email
from email_ui.views import (
    SEARCH_ANYWHERE_FIELDS,
    _ci_variants,
    _clean_query_string,
    _build_back_url,
    _field_tokens,
    _get_list_from_request,
    _q_field_variants,
    _q_token_anywhere,
    _query_tokens,
    _safe_next,
    _sanitize_next_url,
    _split_tokens,
    _token_addresses,
    apply_sorting,
    filter_emails,
)


class SplitTokensTest(TestCase):
    def test_semicolon_and_comma(self):
        self.assertEqual(
            _split_tokens('a@x.ru; b@y.ru ,c@z.ru'),
            ['a@x.ru', 'b@y.ru', 'c@z.ru'])

    def test_empty_and_none(self):
        self.assertEqual(_split_tokens(''), [])
        self.assertEqual(_split_tokens(None), [])
        self.assertEqual(_split_tokens('  , ; '), [])


class TokenAddressesTest(TestCase):
    ADDR = 'kunaev@isetgroup.ru'

    def test_bare_with_trailing_dot(self):
        self.assertEqual(_token_addresses(self.ADDR + '.'), [self.ADDR])

    def test_name_with_brackets(self):
        self.assertEqual(
            _token_addresses(f'Кунаев <{self.ADDR}>'), [self.ADDR])

    def test_two_addresses_in_one_token(self):
        self.assertEqual(
            _token_addresses('a@b.ru c@d.ru'), ['a@b.ru', 'c@d.ru'])

    def test_plain_word_is_not_address(self):
        self.assertEqual(_token_addresses('Кунаев'), [])


class FieldQueryTokensTest(TestCase):
    def test_field_tokens_mixed(self):
        self.assertEqual(
            _field_tokens('a@b.ru, Кунаев'), ['a@b.ru', 'Кунаев'])

    def test_query_tokens_address_flag(self):
        toks = _query_tokens('Аркадий Кунаев <a@b.ru>')
        by_value = {v: flag for v, flag in toks}
        self.assertEqual(by_value.get('Аркадий'), False)
        self.assertEqual(by_value.get('Кунаев'), False)
        self.assertEqual(by_value.get('a@b.ru'), True)

    def test_query_tokens_empty(self):
        self.assertEqual(_query_tokens(''), [])
        self.assertEqual(_query_tokens(None), [])


class CiVariantsTest(TestCase):
    def test_empty(self):
        self.assertEqual(_ci_variants(''), [])
        self.assertEqual(_ci_variants(None), [])

    def test_cyrillic_case_variants(self):
        # FACT (sqlite LIKE ASCII-only): ищем сразу по вариантам регистра.
        variants = _ci_variants('совещание')
        self.assertIn('совещание', variants)
        self.assertIn('Совещание', variants)

    def test_ascii_variants(self):
        variants = _ci_variants('ABC')
        self.assertIn('ABC', variants)
        self.assertIn('abc', variants)


class QBuildersTest(TestCase):
    def test_builders_return_q(self):
        self.assertIsInstance(_q_field_variants('sender', 'a'), Q)
        self.assertIsInstance(_q_token_anywhere('a'), Q)
        self.assertIsInstance(
            _q_token_anywhere('a', include_body=True), Q)

    def test_search_anywhere_fields_pinned(self):
        self.assertEqual(
            set(SEARCH_ANYWHERE_FIELDS),
            {'subject', 'sender', 'sender_name', 'receiver',
             'cc', 'bcc', 'name'})


class FilterFunctionalTest(TestCase):
    """Сквозная проверка Q-хелперов через filter_emails на живых строках."""

    def setUp(self):
        from StaticData.models import Category, Status
        Category.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        Status.objects.get_or_create(pk=1, defaults={'name': 'Default'})
        self.hit = Email.objects.create(
            uid='b25-hit', subject='Совещание по М1',
            sender='kunaev@isetgroup.ru', sender_name='Аркадий Кунаев',
            receiver='strahov@cimrus.com', email_type='IN',
            folder='inbox', sent_status='sent')
        self.other = Email.objects.create(
            uid='b25-other', subject='Совсем другое',
            sender='other@cimrus.com', receiver='strahov@cimrus.com',
            email_type='IN', folder='inbox', sent_status='sent')

    def _ids(self, **params):
        params.setdefault('folder', 'inbox')
        return set(filter_emails(
            Email.objects.filter(folder='inbox'), params
        ).values_list('pk', flat=True))

    def test_cyrillic_lowercase_finds_capitalized(self):
        self.assertIn(self.hit.pk, self._ids(search='совещание'))

    def test_cyrillic_uppercase_finds(self):
        self.assertIn(self.hit.pk, self._ids(search='СОВЕЩАНИЕ'))

    def test_sender_junk_brackets(self):
        self.assertIn(
            self.hit.pk, self._ids(sender='<kunaev@isetgroup.ru>'))
        self.assertNotIn(
            self.other.pk, self._ids(sender='<kunaev@isetgroup.ru>'))

    def test_address_ignores_subject_scope(self):
        self.assertIn(
            self.hit.pk,
            self._ids(search='kunaev@isetgroup.ru', search_scope='subject'))

    def test_word_respects_subject_scope(self):
        # 'Аркадий' только в sender_name — при scope=subject не находится...
        self.assertNotIn(
            self.hit.pk, self._ids(search='Аркадий', search_scope='subject'))
        # ...а слово из темы находится.
        self.assertIn(
            self.other.pk, self._ids(search='другое', search_scope='subject'))


class SortingTest(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _sort(self, **get):
        req = self.rf.get('/fake/', get)
        return apply_sorting(Email.objects.all(), req)

    def test_invalid_field_falls_back_to_stamp(self):
        _qs, field, order = self._sort(sort='nonexistent', order='desc')
        self.assertEqual(field, 'email_stamp')
        self.assertEqual(order, 'desc')

    def test_desc_adds_minus(self):
        qs, field, order = self._sort(sort='sender', order='desc')
        self.assertEqual((field, order), ('sender', 'desc'))
        self.assertEqual(tuple(qs.query.order_by), ('-sender',))

    def test_asc_no_minus(self):
        qs, field, order = self._sort(sort='sender', order='asc')
        self.assertEqual((field, order), ('sender', 'asc'))
        self.assertEqual(tuple(qs.query.order_by), ('sender',))


class SanitizeNextUrlTest(TestCase):
    def test_empty_goes_default(self):
        self.assertEqual(
            _sanitize_next_url(''), reverse('email_ui:inbox_default'))
        self.assertEqual(
            _sanitize_next_url(None), reverse('email_ui:inbox_default'))

    def test_external_goes_default(self):
        self.assertEqual(
            _sanitize_next_url('https://evil.example/x'),
            reverse('email_ui:inbox_default'))

    def test_full_page_passes_through(self):
        url = reverse('email_ui:inbox', args=['inbox']) + '?search=a'
        self.assertEqual(_sanitize_next_url(url), url)

    def test_partial_becomes_full_page(self):
        partial = (reverse('email_ui:email_list_partial')
                   + '?folder=sent&sort=sender')
        result = _sanitize_next_url(partial)
        self.assertNotIn('partial', result)
        self.assertEqual(
            result, reverse('email_ui:inbox', args=['sent']))


class CleanQueryStringTest(TestCase):
    def test_drops_paging_sort_folder_keeps_search(self):
        rf = RequestFactory()
        req = rf.get('/fake/', {'folder': 'inbox', 'search': 'смета',
                                'page': '2', 'sort': 'sender',
                                '_infinite': '1'})
        cleaned = _clean_query_string(req)
        self.assertNotIn('page=', cleaned)
        self.assertNotIn('_infinite', cleaned)
        self.assertNotIn('sort=', cleaned)
        self.assertNotIn('folder=', cleaned)
        self.assertIn('search=', cleaned)

    def test_build_back_url(self):
        rf = RequestFactory()
        req = rf.get('/fake/', {'search': 'смета', 'page': '3'})
        url = _build_back_url(req, folder='inbox')
        self.assertTrue(url.startswith(
            reverse('email_ui:inbox', args=['inbox'])))
        self.assertIn('search=', url)
        self.assertNotIn('page=', url)


class SafeNextTest(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_local_next_redirects_there(self):
        req = self.rf.post('/fake/', {'next': '/email-ui/sent/'})
        resp = _safe_next(req, 'email_ui:inbox_default')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/email-ui/sent/')

    def test_evil_next_falls_back(self):
        req = self.rf.post('/fake/', {'next': 'https://evil.example/'})
        resp = _safe_next(req, 'email_ui:inbox_default')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'],
                         reverse('email_ui:inbox_default'))

    def test_missing_next_falls_back(self):
        req = self.rf.post('/fake/', {})
        resp = _safe_next(req, 'email_ui:inbox_default')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'],
                         reverse('email_ui:inbox_default'))


class ServiceIdentityTest(TestCase):
    """Вынесенные сервисы — те же объекты, что re-export во views (1:1)."""

    def test_query_service_identity(self):
        import email_ui.views as views
        from email_ui.services import query_service as qs
        for name in ('filter_emails', '_split_tokens', '_token_addresses',
                     '_field_tokens', '_query_tokens', '_ci_variants',
                     '_q_field_variants', '_q_token_anywhere'):
            with self.subTest(name=name):
                self.assertIs(getattr(views, name), getattr(qs, name))

    def test_navigation_identity(self):
        import email_ui.views as views
        from email_ui.services import navigation as nav
        for name in ('apply_sorting', '_sanitize_next_url',
                     '_clean_query_string', '_build_back_url', '_safe_next',
                     '_get_list_from_request'):
            with self.subTest(name=name):
                self.assertIs(getattr(views, name), getattr(nav, name))
        self.assertEqual(views.ALLOWED_SORT_FIELDS, nav.ALLOWED_SORT_FIELDS)


class GetListFromRequestTest(TestCase):
    def _req(self, qs):
        return RequestFactory().get(f'/fake/?{qs}')

    def test_multi_params(self):
        self.assertEqual(
            _get_list_from_request(self._req('tag=1&tag=2'), 'tag'),
            ['1', '2'])

    def test_comma_string_stays_single_item(self):
        # FACT: ветка split(',') недостижима (getlist не пуст, когда get
        # truthy) — запятая НЕ делится. Пин факта, не идеала.
        self.assertEqual(
            _get_list_from_request(self._req('tag=a,b'), 'tag'), ['a,b'])

    def test_missing_param_empty(self):
        self.assertEqual(
            _get_list_from_request(self._req('x=1'), 'tag'), [])
