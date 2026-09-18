from django.db import IntegrityError
from django.test import TestCase

from .models import (
    K1Building,
    K1Entry,
    K1Revision,
    M1Building,
    M1ChangeLog,
    M1Check,
    M1Entry,
    M1Issue,
    M1Remark,
    M1Revision,
)
from .services import accdb_row_hash, next_code


class DocRegistryModelTest(TestCase):
    def test_entry_create_and_str(self):
        b = M1Building.objects.create(code=49, number='5.24', name='Площадка буртования')
        e = M1Entry.objects.create(code=379, cipher='ВВ-17-5.24-КЖ1', building=b)
        self.assertEqual(str(e), '379: ВВ-17-5.24-КЖ1')
        self.assertEqual(e.building.name, 'Площадка буртования')
        self.assertEqual(M1Entry.objects.count(), 1)

    def test_revision_chain_ordering(self):
        e = M1Entry.objects.create(code=100, cipher='X')
        M1Revision.objects.create(entry=e, rev_no=2)
        M1Revision.objects.create(entry=e, rev_no=1)
        self.assertEqual(
            list(e.revisions.values_list('rev_no', flat=True)), [1, 2])

    def test_revision_unique_per_entry(self):
        e = M1Entry.objects.create(code=101, cipher='Y')
        M1Revision.objects.create(entry=e, rev_no=1)
        with self.assertRaises(IntegrityError):
            M1Revision.objects.create(entry=e, rev_no=1)

    def test_check_one_to_one(self):
        e = M1Entry.objects.create(code=102, cipher='Z')
        r = M1Revision.objects.create(entry=e, rev_no=1)
        M1Check.objects.create(revision=r, verdict='PASS')
        with self.assertRaises(IntegrityError):
            M1Check.objects.create(revision=r, verdict='FAIL')

    def test_remark_issue_changelog_flow(self):
        e = M1Entry.objects.create(code=103, cipher='W')
        r = M1Revision.objects.create(entry=e, rev_no=1, status='has_remarks')
        M1Remark.objects.create(revision=r, text='Высота стен не та')
        M1Issue.objects.create(entry=e, waybill_no='201', network_path='//srv/ptr')
        M1ChangeLog.objects.create(entry=e, field='status', old_value='received', new_value='issued', source='api')
        self.assertEqual(r.remarks.count(), 1)
        self.assertEqual(e.issues.count(), 1)
        self.assertEqual(e.changelog.count(), 1)

    def test_next_code_empty_and_filled(self):
        self.assertEqual(next_code(M1Entry), 1)
        M1Entry.objects.create(code=379, cipher='Q')
        self.assertEqual(next_code(M1Entry), 380)

    def test_row_hash_stable_and_sensitive(self):
        v = {'code': 379, 'cipher': 'A', 'section': '8'}
        self.assertEqual(accdb_row_hash(v), accdb_row_hash(dict(v)))
        v2 = dict(v, cipher='B')
        self.assertNotEqual(accdb_row_hash(v), accdb_row_hash(dict(v2)))


class DocApiFlowTest(TestCase):
    """Сквозной флоу агента в реестре объекта: intake → validate → register → issue."""

    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user('agent', 'a@a.a', 'pw')
        self.client.force_login(self.user)
        from Emails.models import Email
        self.email = Email.objects.create(subject='Чертежи КЖ1', sender='podr@x.ru', category=None)

    def _mock_engine(self, podano_verdict='OK'):
        from unittest.mock import patch
        from DocRegistry import designbase_client as dbc
        calls = {'n': 0}

        def fake(path, params=None, payload=None, timeout=60):
            calls['n'] += 1
            if 'diff' in path:
                return {'hint': 'CHANGED', 'changed_pages': [2]}
            if 'pechat' in path:
                return {'found': True, 'exact_match': True, 'matches': []}
            if 'podano' in path:
                return {'code': 500, 'verdict': podano_verdict,
                        'row': {'Дата подачи на согласование': '2026-09-01'},
                        'matched_folder': '2026-09-01_Test'}
            if 'dds' in path:
                return {'cipher': 'X', 'rows': []}
            return {}
        return patch.object(dbc, 'get', side_effect=lambda p, params=None, timeout=60: fake(p, params)), \
            patch.object(dbc, 'post', side_effect=lambda p, payload=None, timeout=120: fake(p, None, payload))

    def test_full_flow(self):
        r = self.client.post('/api/docs/M1/intake/', {'email_id': self.email.pk}, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        rev = r.json()['id']
        self.assertIsNone(r.json()['entry'])

        get_p, post_p = self._mock_engine()
        with get_p, post_p:
            v = self.client.post(f'/api/docs/M1/{rev}/validate/', {}, content_type='application/json')
        self.assertEqual(v.status_code, 200)
        self.assertEqual(v.json()['verdict'], 'PASS')
        self.assertEqual(v.json()['status'], 'checked_ok')

        # без confirm новая запись — 400 c next_code
        r400 = self.client.post(f'/api/docs/M1/{rev}/register/', {}, content_type='application/json')
        self.assertEqual(r400.status_code, 400)
        self.assertEqual(r400.json()['next_code'], 1)
        reg = self.client.post(f'/api/docs/M1/{rev}/register/', {'confirm': True},
                               content_type='application/json')
        self.assertEqual(reg.status_code, 200)
        self.assertEqual(reg.json()['status'], 'registered')
        self.assertEqual(reg.json()['project'], 'M1')

        iss = self.client.post(f'/api/docs/M1/{rev}/issue/', {'waybill_no': '301'}, content_type='application/json')
        self.assertEqual(iss.status_code, 201)
        self.assertEqual(M1Revision.objects.get(pk=rev).status, 'issued')

        q = self.client.get('/api/docs/M1/queue/')
        self.assertEqual(q.status_code, 200)
        self.assertIn('received', q.json())

        card = self.client.get(f'/api/docs/M1/entry/{reg.json()["entry"]}/')
        self.assertEqual(card.status_code, 200)
        self.assertEqual(len(card.json()['revisions']), 1)
        self.assertEqual(len(card.json()['issues']), 1)

    def test_registries_isolated_in_api(self):
        """Ревизия М1 не видна через К1-маршруты и наоборот."""
        r = self.client.post('/api/docs/M1/intake/', {'email_id': self.email.pk}, content_type='application/json')
        rev = r.json()['id']
        bad = self.client.post(f'/api/docs/K1/{rev}/validate/', {}, content_type='application/json')
        self.assertEqual(bad.status_code, 404)
        q = self.client.get('/api/docs/K1/queue/')
        self.assertEqual(q.json()['counts']['received'], 0)

    def test_unknown_project_404(self):
        r = self.client.post('/api/docs/ZZ/intake/', {'email_id': self.email.pk},
                             content_type='application/json')
        self.assertEqual(r.status_code, 404)

    def test_validate_no_code_fails(self):
        r = self.client.post('/api/docs/M1/intake/', {'email_id': self.email.pk}, content_type='application/json')
        rev = r.json()['id']
        get_p, post_p = self._mock_engine(podano_verdict='NO_CODE')
        with get_p, post_p:
            v = self.client.post(f'/api/docs/M1/{rev}/validate/', {'code': 500}, content_type='application/json')
        self.assertEqual(v.json()['verdict'], 'FAIL')
        self.assertEqual(v.json()['status'], 'has_remarks')
        # замечание вручную
        rm = self.client.post(f'/api/docs/M1/{rev}/remarks/', {'text': 'Нет в accdb'}, content_type='application/json')
        self.assertEqual(rm.status_code, 201)
        # выдача из has_remarks запрещена
        iss = self.client.post(f'/api/docs/M1/{rev}/issue/', {'waybill_no': '1'}, content_type='application/json')
        self.assertEqual(iss.status_code, 400)

    def test_validate_unreachable_503(self):
        from unittest.mock import patch
        from DocRegistry import designbase_client as dbc
        r = self.client.post('/api/docs/M1/intake/', {'email_id': self.email.pk}, content_type='application/json')
        rev = r.json()['id']
        with patch.object(dbc, 'get', side_effect=dbc.DesignBaseUnreachable('down')), \
                patch.object(dbc, 'post', side_effect=dbc.DesignBaseUnreachable('down')):
            v = self.client.post(f'/api/docs/M1/{rev}/validate/', {'code': 500}, content_type='application/json')
        self.assertEqual(v.status_code, 503)

    def test_unauthorized(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/docs/M1/queue/').status_code, 401)


class DocUiTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user('uiviewer', 'u@u.u', 'pw')
        self.client.force_login(self.user)
        self.entry = M1Entry.objects.create(code=501, cipher='ВВ-17-1.1-АР1')
        self.rev = M1Revision.objects.create(entry=self.entry, rev_no=1, status='has_remarks')
        self.remark = M1Remark.objects.create(revision=self.rev, text='Стены не те')
        self.issue = M1Issue.objects.create(entry=self.entry, waybill_no='301')

    def test_queue_page(self):
        r = self.client.get('/docs/M1/queue/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ВВ-17-1.1-АР1')
        self.assertContains(r, 'Замечания')

    def test_revision_page(self):
        r = self.client.get(f'/docs/M1/revision/{self.rev.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Стены не те')
        self.assertContains(r, '/api/docs/')
        self.assertContains(r, 'var PROJECT="M1"')

    def test_entry_page(self):
        r = self.client.get('/docs/M1/entry/501/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ВВ-17-1.1-АР1')
        self.assertContains(r, 'Накладная №301')

    def test_other_project_does_not_see(self):
        self.assertEqual(self.client.get(f'/docs/K1/revision/{self.rev.pk}/').status_code, 404)
        self.assertEqual(self.client.get('/docs/K1/entry/501/').status_code, 404)
        r = self.client.get('/docs/K1/queue/')
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'ВВ-17-1.1-АР1')

    def test_queue_login_required(self):
        self.client.logout()
        r = self.client.get('/docs/M1/queue/')
        self.assertEqual(r.status_code, 302)


class DocReferenceTest(TestCase):
    def setUp(self):
        import shutil
        import tempfile
        from django.test import override_settings
        # PDF-вьюхи сохраняют файлы на диск — только во временный каталог, не в живую Переписку
        self._media = tempfile.mkdtemp(prefix='docreg_test_')
        self._media_override = override_settings(MEDIA_ROOT=self._media)
        self._media_override.enable()
        self.addCleanup(self._media_override.disable)
        self.addCleanup(shutil.rmtree, self._media, True)
        from .models import DocDeveloper, DocSection, DocSigner
        self.b = M1Building.objects.create(code=4, number='1.4', name='Коровник  № 4')
        self.s = DocSection.objects.create(code=21, short='ВК', name='Внутренние системы ВиК')
        self.d = DocDeveloper.objects.create(code=1, name='ДеЛаваль')
        DocSigner.objects.create(order=1, position='Менеджер по проектированию',
                                 company='ООО «СИМРУС»', person='Страхов С.')

    def test_entry_fk_resolution_like_accdb_row_1(self):
        e = M1Entry.objects.create(
            code=1, cipher='ВВ-17.К-1.1-ВК', section=self.s,
            building_no=self.b, building=self.b, developer=self.d,
            approval_status='согласовано')
        self.assertEqual(e.section.short, 'ВК')
        self.assertEqual(e.building_no.number, '1.4')
        self.assertEqual(e.building.name, 'Коровник  № 4')
        self.assertEqual(e.developer.name, 'ДеЛаваль')

    def test_signers_global_list(self):
        from .models import DocSigner
        from .services import signers_for
        DocSigner.objects.create(order=2, position='Прораб', person='Иванов И.')
        signers = signers_for()
        self.assertEqual(len(signers), 2)
        self.assertEqual(signers[0].person, 'Страхов С.')  # order=1 первый
        self.assertEqual(signers[1].person, 'Иванов И.')

    def test_approval_sheet_pdf(self):
        from django.contrib.auth.models import User
        from .services import signers_for
        user = User.objects.create_user('appr', 'p@p.p', 'pw')
        self.client.force_login(user)
        e = M1Entry.objects.create(
            code=2, cipher='ВВ-17-1.3-АПС1', section=self.s,
            building=self.b, building_no=self.b, developer=self.d)
        iss = M1Issue.objects.create(entry=e, waybill_no='305')
        r = self.client.get(f'/docs/M1/issue/{iss.pk}/approval.pdf')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        content = b''.join(r.streaming_content)
        self.assertTrue(content.startswith(b'%PDF'))

    def test_remark_sheet_pdf(self):
        from django.contrib.auth.models import User
        user = User.objects.create_user('appr2', 'p2@p.p', 'pw')
        self.client.force_login(user)
        e = M1Entry.objects.create(
            code=20, cipher='ВВ-17-1.3-АР1', section=self.s,
            building=self.b, building_no=self.b, developer=self.d)
        rev = M1Revision.objects.create(entry=e, rev_no=1, status='has_remarks')
        rm = M1Remark.objects.create(revision=rev, text='Ось Б смещена')
        r = self.client.get(f'/docs/M1/remark/{rm.pk}/sheet.pdf')
        self.assertEqual(r.status_code, 200)
        content = b''.join(r.streaming_content)
        self.assertTrue(content.startswith(b'%PDF'))
        rm.refresh_from_db()
        self.assertTrue(rm.sheet_pdf.name.endswith('.pdf'))

    def test_waybill_pdf_and_issue_approval(self):
        from django.contrib.auth.models import User
        user = User.objects.create_user('appr3', 'p3@p.p', 'pw')
        self.client.force_login(user)
        e = M1Entry.objects.create(
            code=30, cipher='ВВ-17-1.4-КЖ1', building=self.b, section=self.s)
        iss = M1Issue.objects.create(entry=e, waybill_no='310', network_path='//srv/ptr')
        r = self.client.get(f'/docs/M1/issue/{iss.pk}/waybill.pdf')
        self.assertEqual(r.status_code, 200)
        content = b''.join(r.streaming_content)
        self.assertTrue(content.startswith(b'%PDF'))
        iss.refresh_from_db()
        self.assertTrue(iss.waybill_pdf.name.endswith('.pdf'))
        r = self.client.get(f'/docs/M1/issue/{iss.pk}/approval.pdf')
        self.assertEqual(r.status_code, 200)
        iss.refresh_from_db()
        self.assertTrue(iss.approval_pdf.name.endswith('.pdf'))

    def test_stamp_in_signature_cell(self):
        from .models import DocSigner
        from .pdf_forms import approval_sheet_multi
        from .services import signers_for
        DocSigner.objects.create(order=1, position='Менеджер по проектированию',
                                 company='ООО «СИМРУС»', person='Страхов С.', stamp=True)
        e = M1Entry.objects.create(code=41, cipher='S')
        text = self._pdf_text(approval_sheet_multi([e], signers_for()))
        self.assertIn('СОГЛАСОВАНО', text)
        self.assertIn('Страхов С.', text)

    def test_design_manager_autograph_embedded(self):
        """В ячейку подписи менеджера по проектированию встроен автограф (PNG)."""
        from .pdf_forms import approval_sheet_multi
        from .services import signers_for
        e = M1Entry.objects.create(code=42, cipher='S2')
        pdf = approval_sheet_multi([e], signers_for())
        import pymupdf
        doc = pymupdf.open(stream=pdf, filetype='pdf')
        try:
            images = doc[0].get_images(full=True)
        finally:
            doc.close()
        self.assertTrue(images, 'Автограф менеджера по проектированию должен быть встроен в PDF')

    def test_buildings_per_object_tables(self):
        from django.db import transaction
        M1Building.objects.create(code=7, number='2.1', name='Телятник № 1')
        # тот же номер у К1 — другая таблица, ок
        K1Building.objects.create(code=7, number='9.9', name='Телятник № 5')
        self.assertEqual(M1Building.objects.filter(code=7).count(), 1)
        self.assertEqual(K1Building.objects.filter(code=7).count(), 1)
        # дубль внутри таблицы запрещён
        with transaction.atomic(), self.assertRaises(IntegrityError):
            M1Building.objects.create(code=7, number='2.1-дубль')

    def test_admin_display_methods(self):
        from .admin import M1EntryAdmin
        from django.contrib import admin as dj_admin
        e = M1Entry.objects.create(
            code=3, cipher='X', section=self.s,
            building_no=self.b, building=self.b, developer=self.d)
        ma = M1EntryAdmin(M1Entry, dj_admin.site)
        self.assertEqual(ma.get_building(e), 'Коровник  № 4')
        self.assertEqual(ma.get_section(e), 'ВК')
        self.assertEqual(ma.get_building_no(e), '1.4')
        self.assertEqual(ma.get_developer(e), 'ДеЛаваль')
        e2 = M1Entry.objects.create(code=4, cipher='Y')
        self.assertEqual(ma.get_building(e2), '—')

    def test_admin_action_approval_sheet(self):
        from django.contrib.auth.models import User
        User.objects.create_superuser('boss', 'b@b.b', 'pw')
        self.client.force_login(User.objects.get(username='boss'))
        e1 = M1Entry.objects.create(
            code=11, cipher='ВВ-17-1-АР1', building=self.b, section=self.s, developer=self.d)
        e2 = M1Entry.objects.create(
            code=12, cipher='ВВ-17-2-АР1', building=self.b, section=self.s, developer=self.d)
        r = self.client.post('/admin/DocRegistry/m1entry/', {
            'action': 'make_approval_sheet', '_selected_action': [e1.pk, e2.pk]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_approval_multi_global_signers(self):
        from .pdf_forms import approval_sheet_multi
        from .services import signers_for
        e = M1Entry.objects.create(
            code=13, cipher='ВВ-17-3-АР1', building=self.b, section=self.s)
        pdf = approval_sheet_multi([e], signers_for())
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertGreater(len(pdf), 3000)

    def _pdf_text(self, pdf: bytes) -> str:
        import pymupdf
        doc = pymupdf.open(stream=pdf, filetype='pdf')
        try:
            return '\n'.join(p.get_text() for p in doc)
        finally:
            doc.close()

    def test_approval_header_single_project(self):
        from .models import DocProject
        from .pdf_forms import approval_sheet_multi
        from .services import signers_for
        DocProject.objects.update_or_create(
            code='M1', defaults={'name': 'Волоколамск',
                                 'customer': 'ООО «ТиЭйч-РУС Милк Фуд»',
                                 'object_name': 'Комплекс МЖК',
                                 'object_address': 'Волоколамский район',
                                 'designer': 'ИП РОДИН'})
        e = M1Entry.objects.create(
            code=21, cipher='ВВ-17-9-АР1', building=self.b)
        text = self._pdf_text(approval_sheet_multi([e], signers_for()))
        self.assertIn('Волоколамский район', text)
        self.assertIn('ИП РОДИН', text)

    def test_approval_section2_from_registry(self):
        from .pdf_forms import approval_sheet_multi
        from .services import signers_for
        e = M1Entry.objects.create(
            code=61, cipher='ВВ-17-9-ВК1', building=self.b, section=self.s,
            file_name='ВВ-17-1.9-ВК Изм4.pdf', change_descr='Добавлена канализация')
        text = self._pdf_text(approval_sheet_multi([e], signers_for()))
        self.assertIn('Коровник', text)
        self.assertIn('1.4', text)
        self.assertIn('ВК', text)
        self.assertIn('ВВ-17-1.9-ВК Изм4.pdf', text)
        self.assertIn('Добавлена канализация', text)

    def test_approval_note_tom_only_single_cipher(self):
        from .pdf_forms import approval_sheet_multi
        from .services import signers_for
        a = M1Entry.objects.create(code=51, cipher='ТОМ-1')
        b = M1Entry.objects.create(code=52, cipher='ТОМ-1')
        c = M1Entry.objects.create(code=53, cipher='')
        self.assertIn('общий том', self._pdf_text(approval_sheet_multi([a, b], signers_for())))
        self.assertNotIn('общий том', self._pdf_text(approval_sheet_multi([a, c], signers_for())))

    def test_approval_header_multi_projects_table(self):
        from .models import DocProject
        from .pdf_forms import approval_sheet_multi
        from .services import signers_for
        DocProject.objects.update_or_create(
            code='M1', defaults={'name': 'Волоколамск', 'customer': 'Заказчик-М1'})
        DocProject.objects.update_or_create(
            code='K1', defaults={'name': 'Калуга', 'customer': 'Заказчик-К1'})
        e1 = M1Entry.objects.create(code=22, cipher='A')
        e2 = K1Entry.objects.create(code=23, cipher='B')
        text = self._pdf_text(approval_sheet_multi([e1, e2], signers_for()))
        self.assertIn('Волоколамск', text)
        self.assertIn('Калуга', text)
        self.assertIn('Заказчик-К1', text)


class DocSplitTest(TestCase):
    """Физическое разделение: таблицы М1/К1 не смешиваются конструктивно."""

    def test_same_code_in_both_registries(self):
        M1Entry.objects.create(code=1, cipher='M')
        K1Entry.objects.create(code=1, cipher='K')
        self.assertEqual(M1Entry.objects.get(code=1).cipher, 'M')
        self.assertEqual(K1Entry.objects.get(code=1).cipher, 'K')

    def test_next_code_independent(self):
        M1Entry.objects.create(code=5, cipher='M')
        self.assertEqual(next_code(M1Entry), 6)
        self.assertEqual(next_code(K1Entry), 1)

    def test_cross_object_fk_impossible(self):
        kb = K1Building.objects.create(code=4, number='7', name='Коровник № 7')
        with self.assertRaises(ValueError):
            M1Entry.objects.create(code=2, cipher='M', building=kb)

    def test_entry_project_property(self):
        from .models import DocProject
        DocProject.objects.update_or_create(code='M1', defaults={'name': 'Волоколамск'})
        DocProject.objects.update_or_create(code='K1', defaults={'name': 'Калуга'})
        self.assertEqual(M1Entry.objects.create(code=3, cipher='M').project.code, 'M1')
        self.assertEqual(K1Entry.objects.create(code=3, cipher='K').project.code, 'K1')
        self.assertEqual(M1Entry.objects.create(code=4, cipher='M2').project_id, 'M1')

    def test_registry_map(self):
        from django.http import Http404
        from .models import get_registry_or_404
        self.assertIs(get_registry_or_404('M1')['entry'], M1Entry)
        self.assertIs(get_registry_or_404('K1')['revision'], K1Revision)
        with self.assertRaises(Http404):
            get_registry_or_404('ZZ')

    def test_building_type_shared(self):
        from .services import get_building_type
        t1 = get_building_type('Коровник № 4')
        t2 = get_building_type('Коровник № 7')
        self.assertIsNotNone(t1)
        self.assertEqual(t1.pk, t2.pk)
        M1Building.objects.create(code=4, number='1.4', name='Коровник № 4',
                                  building_type=t1)
        K1Building.objects.create(code=4, number='7', name='Коровник № 7',
                                  building_type=t2)
        self.assertEqual(M1Building.objects.get(code=4).building_type_id, t1.pk)
        self.assertEqual(K1Building.objects.get(code=4).building_type_id, t1.pk)

    def test_admin_changelists_separated(self):
        from django.contrib.auth.models import User
        User.objects.create_superuser('scope', 's@s.s', 'pw')
        self.client.force_login(User.objects.get(username='scope'))
        M1Entry.objects.create(code=1, cipher='M1DOC')
        K1Entry.objects.create(code=1, cipher='K1DOC')
        r = self.client.get('/admin/DocRegistry/m1entry/')
        self.assertContains(r, 'M1DOC')
        self.assertNotContains(r, 'K1DOC')
        r = self.client.get('/admin/DocRegistry/k1entry/')
        self.assertContains(r, 'K1DOC')
        self.assertNotContains(r, 'M1DOC')

    def test_admin_all_changelists_render(self):
        from django.contrib.auth.models import User
        User.objects.create_superuser('scope3', 's3@s.s', 'pw')
        self.client.force_login(User.objects.get(username='scope3'))
        for model in ('m1entry', 'k1entry', 'm1building', 'k1building',
                      'm1revision', 'k1revision', 'm1check', 'k1check',
                      'm1remark', 'k1remark', 'm1issue', 'k1issue',
                      'm1changelog', 'k1changelog', 'docproject',
                      'docsection', 'docdeveloper', 'docsigner'):
            r = self.client.get(f'/admin/DocRegistry/{model}/')
            self.assertEqual(r.status_code, 200, model)
        r = self.client.get('/admin/DocRegistry/m1entry/add/')
        self.assertEqual(r.status_code, 200)

    def test_upload_paths_split_by_project(self):
        import shutil
        import tempfile
        from django.core.files.base import ContentFile
        from django.test import override_settings
        from .models import K1Issue, M1Issue
        media = tempfile.mkdtemp(prefix='docreg_split_')
        try:
            with override_settings(MEDIA_ROOT=media):
                e_m1 = M1Entry.objects.create(code=90, cipher='M')
                e_k1 = K1Entry.objects.create(code=90, cipher='K')
                r_m1 = M1Revision.objects.create(entry=e_m1)
                r_m1.file.save('chertezh.pdf', ContentFile(b'%PDF-m1'), save=True)
                r_k1 = K1Revision.objects.create(entry=e_k1)
                r_k1.file.save('chertezh.pdf', ContentFile(b'%PDF-k1'), save=True)
                self.assertTrue(r_m1.file.name.startswith('DocRegistry/M1/incoming/'))
                self.assertTrue(r_k1.file.name.startswith('DocRegistry/K1/incoming/'))
                i_m1 = M1Issue.objects.create(entry=e_m1, waybill_no='1')
                i_m1.waybill_pdf.save('nakl.pdf', ContentFile(b'%PDF-w'), save=True)
                self.assertTrue(i_m1.waybill_pdf.name.startswith('DocRegistry/M1/issues/'))
                i_k1 = K1Issue.objects.create(entry=e_k1, waybill_no='1')
                i_k1.waybill_pdf.save('nakl.pdf', ContentFile(b'%PDF-wk'), save=True)
                self.assertTrue(i_k1.waybill_pdf.name.startswith('DocRegistry/K1/issues/'))
                # физически разные файлы
                self.assertNotEqual(r_m1.file.path, r_k1.file.path)
                self.assertNotEqual(i_m1.waybill_pdf.path, i_k1.waybill_pdf.path)
        finally:
            shutil.rmtree(media, ignore_errors=True)

    def test_entry_filters_by_building_section_number(self):
        from django.contrib.auth.models import User
        User.objects.create_superuser('flt', 'f@f.ff', 'pw')
        self.client.force_login(User.objects.get(username='flt'))
        from .models import DocSection
        s = DocSection.objects.create(code=21, short='ВК', name='ВиК')
        b1 = M1Building.objects.create(code=4, number='1.4', name='Коровник № 4')
        b2 = M1Building.objects.create(code=7, number='2.1', name='Телятник № 1')
        M1Entry.objects.create(code=1, cipher='DOC-A', section=s, building=b1, building_no=b1)
        M1Entry.objects.create(code=2, cipher='DOC-B', building=b2, building_no=b2)
        url = '/admin/DocRegistry/m1entry/'
        # заголовки фильтров на месте
        r = self.client.get(url)
        self.assertContains(r, 'Наименование здания')
        self.assertContains(r, 'Номер здания')
        self.assertContains(r, 'Раздел')
        # фильтр по зданию
        r = self.client.get(url + f'?building__id__exact={b1.pk}')
        self.assertContains(r, 'DOC-A')
        self.assertNotContains(r, 'DOC-B')
        # фильтр по номеру здания показывает №, а не наименование
        r = self.client.get(url + f'?building_no__id__exact={b2.pk}')
        self.assertContains(r, 'DOC-B')
        self.assertNotContains(r, 'DOC-A')
        self.assertContains(self.client.get(url), '2.1')
        # фильтр по разделу (PK раздела — code, не id)
        r = self.client.get(url + f'?section__code__exact={s.pk}')
        self.assertContains(r, 'DOC-A')
        self.assertNotContains(r, 'DOC-B')
        from .serializers import entry_serializer_for
        e = M1Entry.objects.create(code=9, cipher='S')
        data = entry_serializer_for(M1Entry)(e).data
        self.assertEqual(data['project'], 'M1')
        self.assertEqual(data['code'], 9)

    def test_admin_panels_separated(self):
        from django.contrib.auth.models import User
        User.objects.create_superuser('panels', 'pn@pn.pn', 'pw')
        self.client.force_login(User.objects.get(username='panels'))
        M1Entry.objects.create(code=1, cipher='M1DOC')
        # индекс М1: свой реестр есть, чужого нет
        r = self.client.get('/admin-m1/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Реестр М1')
        self.assertNotContains(r, 'Реестр К1')
        # индекс К1 — наоборот
        r = self.client.get('/admin-k1/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Реестр К1')
        self.assertNotContains(r, 'Реестр М1')
        # чейнджлисты свои открываются, чужие — 404
        self.assertContains(self.client.get('/admin-m1/DocRegistry/m1entry/'), 'M1DOC')
        self.assertEqual(self.client.get('/admin-m1/DocRegistry/k1entry/').status_code, 404)
        self.assertEqual(self.client.get('/admin-k1/DocRegistry/m1entry/').status_code, 404)
        self.assertEqual(self.client.get('/admin-k1/DocRegistry/k1entry/').status_code, 200)
        # общие справочники — в обеих панелях
        self.assertEqual(self.client.get('/admin-m1/DocRegistry/docsection/').status_code, 200)
        self.assertEqual(self.client.get('/admin-k1/DocRegistry/docsection/').status_code, 200)

    def test_main_admin_index_grouped(self):
        from django.contrib.auth.models import User
        User.objects.create_superuser('idx', 'ix@ix.ix', 'pw')
        self.client.force_login(User.objects.get(username='idx'))
        r = self.client.get('/admin/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Реестр М1')
        self.assertContains(r, 'Реестр К1')
        self.assertContains(r, 'Справочники РД')
        # страница приложения не сломана
        r = self.client.get('/admin/DocRegistry/')
        self.assertEqual(r.status_code, 200)


class DocDriftMappingTest(TestCase):
    def test_compare_ok(self):
        from .services import compare_registry
        live = [{'code': 1, 'accdb_row_hash': 'a'}, {'code': 2, 'accdb_row_hash': 'b'}]
        rep = compare_registry(live, {1: 'a', 2: 'b'})
        self.assertTrue(rep['ok'])

    def test_compare_new_changed_missing(self):
        from .services import compare_registry
        live = [{'code': 1, 'accdb_row_hash': 'a!'}, {'code': 3, 'accdb_row_hash': 'c'}]
        rep = compare_registry(live, {1: 'a', 2: 'b'})
        self.assertFalse(rep['ok'])
        self.assertEqual(rep['changed'], [1])
        self.assertEqual(rep['new'], [3])
        self.assertEqual(rep['missing'], [2])

    def test_match_score(self):
        from DocRegistry.management.commands.suggest_task_mapping import match_score
        self.assertEqual(match_score('', 'что угодно'), 0.0)
        s = match_score('Коровник КЖ замена светильников чертеж',
                        'Замена светильников в коровнике №1 и №2')
        self.assertGreaterEqual(s, 0.5)
        self.assertLess(match_score('Телятник ЭМ розетки', 'Коровник КЖ балки'), 0.5)

    def test_drift_command_ok_and_fail(self):
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command, CommandError
        with patch('DocRegistry.accdb.read_registry_rows',
                   return_value=[{'code': 7, 'accdb_row_hash': 'h7'}]):
            M1Entry.objects.create(code=7, cipher='T', accdb_row_hash='h7')
            out = StringIO()
            call_command('check_accdb_drift', '--project', 'M1', stdout=out)
            self.assertIn('drift OK', out.getvalue())
            M1Entry.objects.create(code=8, cipher='U', accdb_row_hash='h8')
            with self.assertRaises(CommandError):
                call_command('check_accdb_drift', '--project', 'M1', stdout=StringIO())

    def test_drift_ignores_other_registry(self):
        """Строка К1 с тем же кодом не ломает drift М1."""
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command
        with patch('DocRegistry.accdb.read_registry_rows',
                   return_value=[{'code': 7, 'accdb_row_hash': 'h7'}]):
            M1Entry.objects.create(code=7, cipher='T', accdb_row_hash='h7')
            K1Entry.objects.create(code=7, cipher='K', accdb_row_hash='ДРУГОЙ')
            out = StringIO()
            call_command('check_accdb_drift', '--project', 'M1', stdout=out)
            self.assertIn('drift OK', out.getvalue())
