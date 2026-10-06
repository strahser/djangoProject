# -*- coding: utf-8 -*-
"""Блок 11: гарды изоляции реестров М1/К1 (админки + очереди)."""
from django.contrib.auth.models import User
from django.test import TestCase

from .admin_sites import k1_site, m1_site
from .models import (
    DocDeveloper,
    DocProject,
    DocSection,
    DocSigner,
    K1Building,
    K1Entry,
    K1Revision,
    M1Building,
    M1Entry,
    M1Revision,
)


class SiteRegistryTest(TestCase):
    def _models(self, site):
        return set(site._registry.keys())

    def test_m1_has_no_k1_models(self):
        models = self._models(m1_site)
        self.assertIn(M1Entry, models)
        self.assertIn(M1Building, models)
        self.assertNotIn(K1Entry, models)
        self.assertNotIn(K1Building, models)

    def test_k1_has_no_m1_models(self):
        models = self._models(k1_site)
        self.assertIn(K1Entry, models)
        self.assertIn(K1Building, models)
        self.assertNotIn(M1Entry, models)
        self.assertNotIn(M1Building, models)

    def test_shared_models_in_both(self):
        for model in (DocProject, DocSection, DocDeveloper, DocSigner):
            self.assertIn(model, self._models(m1_site))
            self.assertIn(model, self._models(k1_site))

    def test_admin_smoke(self):
        boss = User.objects.create_superuser(
            username='b11_boss', password='pw', email='b@b.b')
        self.client.force_login(boss)
        for url in ('/admin-m1/', '/admin-k1/'):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)

    def test_admin_anonymous_redirects(self):
        for url in ('/admin-m1/', '/admin-k1/'):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302)


class QueueIsolationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='b11', password='pw')
        cls.s = DocSection.objects.create(code=21, short='ВК', name='ВиК')
        cls.d = DocDeveloper.objects.create(code=1, name='ДеЛаваль')
        cls.mb = M1Building.objects.create(code=4, number='1.4', name='М1-цех')
        cls.kb = K1Building.objects.create(code=7, number='2.1', name='К1-цех')
        me = M1Entry.objects.create(
            code=1, cipher='М1-ШИФР', section=cls.s,
            building_no=cls.mb, building=cls.mb, developer=cls.d)
        ke = K1Entry.objects.create(
            code=1, cipher='К1-ШИФР', section=cls.s,
            building_no=cls.kb, building=cls.kb, developer=cls.d)
        M1Revision.objects.create(entry=me, rev_no=1, status='received')
        K1Revision.objects.create(entry=ke, rev_no=1, status='received')

    def setUp(self):
        self.client.force_login(self.user)

    def test_each_queue_sees_only_own(self):
        m1 = self.client.get('/docs/M1/queue/')
        k1 = self.client.get('/docs/K1/queue/')
        self.assertEqual(m1.status_code, 200)
        self.assertEqual(k1.status_code, 200)
        self.assertContains(m1, 'М1-ШИФР')
        self.assertNotContains(m1, 'К1-ШИФР')
        self.assertContains(k1, 'К1-ШИФР')
        self.assertNotContains(k1, 'М1-ШИФР')
