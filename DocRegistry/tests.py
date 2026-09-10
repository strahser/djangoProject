from django.db import IntegrityError
from django.test import TestCase

from .models import (
    DocChangeLog,
    DocCheck,
    DocIssue,
    DocRegisterEntry,
    DocRemark,
    DocRevision,
)
from .services import accdb_row_hash, next_code


class DocRegistryModelTest(TestCase):
    def test_entry_create_and_str(self):
        from .models import DocBuilding
        b = DocBuilding.objects.create(code=49, number='5.24', name='Площадка буртования')
        e = DocRegisterEntry.objects.create(code=379, cipher='ВВ-17-5.24-КЖ1', building=b)
        self.assertEqual(str(e), '379: ВВ-17-5.24-КЖ1')
        self.assertEqual(e.building.name, 'Площадка буртования')
        self.assertEqual(DocRegisterEntry.objects.count(), 1)

    def test_revision_chain_ordering(self):
        e = DocRegisterEntry.objects.create(code=100, cipher='X')
        DocRevision.objects.create(entry=e, rev_no=2)
        DocRevision.objects.create(entry=e, rev_no=1)
        self.assertEqual(
            list(e.revisions.values_list('rev_no', flat=True)), [1, 2])

    def test_revision_unique_per_entry(self):
        e = DocRegisterEntry.objects.create(code=101, cipher='Y')
        DocRevision.objects.create(entry=e, rev_no=1)
        with self.assertRaises(IntegrityError):
            DocRevision.objects.create(entry=e, rev_no=1)

    def test_check_one_to_one(self):
        e = DocRegisterEntry.objects.create(code=102, cipher='Z')
        r = DocRevision.objects.create(entry=e, rev_no=1)
        DocCheck.objects.create(revision=r, verdict='PASS')
        with self.assertRaises(IntegrityError):
            DocCheck.objects.create(revision=r, verdict='FAIL')

    def test_remark_issue_changelog_flow(self):
        e = DocRegisterEntry.objects.create(code=103, cipher='W')
        r = DocRevision.objects.create(entry=e, rev_no=1, status='has_remarks')
        DocRemark.objects.create(revision=r, text='Высота стен не та')
        DocIssue.objects.create(entry=e, waybill_no='201', network_path='//srv/ptr')
        DocChangeLog.objects.create(entry=e, field='status', old_value='received', new_value='issued', source='api')
        self.assertEqual(r.remarks.count(), 1)
        self.assertEqual(e.issues.count(), 1)
        self.assertEqual(e.changelog.count(), 1)

    def test_next_code_empty_and_filled(self):
        self.assertEqual(next_code(), 1)
        DocRegisterEntry.objects.create(code=379, cipher='Q')
        self.assertEqual(next_code(), 380)

    def test_row_hash_stable_and_sensitive(self):
        v = {'code': 379, 'cipher': 'A', 'section': '8'}
        self.assertEqual(accdb_row_hash(v), accdb_row_hash(dict(v)))
        v2 = dict(v, cipher='B')
        self.assertNotEqual(accdb_row_hash(v), accdb_row_hash(v2))


class DocApiFlowTest(TestCase):
    """Сквозной флоу агента: intake → validate → register → issue (+remarks, queue, card)."""

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
        from DocRegistry.models import DocRevision
        r = self.client.post('/api/docs/intake/', {'email_id': self.email.pk}, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        rev = r.json()['id']
        self.assertIsNone(r.json()['entry'])

        get_p, post_p = self._mock_engine()
        with get_p, post_p:
            v = self.client.post(f'/api/docs/{rev}/validate/', {}, content_type='application/json')
        self.assertEqual(v.status_code, 200)
        self.assertEqual(v.json()['verdict'], 'PASS')
        self.assertEqual(v.json()['status'], 'checked_ok')

        # без confirm новая запись — 400
        r400 = self.client.post(f'/api/docs/{rev}/register/', {}, content_type='application/json')
        self.assertEqual(r400.status_code, 400)
        reg = self.client.post(f'/api/docs/{rev}/register/', {'confirm': True}, content_type='application/json')
        self.assertEqual(reg.status_code, 200)
        self.assertEqual(reg.json()['status'], 'registered')

        iss = self.client.post(f'/api/docs/{rev}/issue/', {'waybill_no': '301'}, content_type='application/json')
        self.assertEqual(iss.status_code, 201)
        self.assertEqual(DocRevision.objects.get(pk=rev).status, 'issued')

        q = self.client.get('/api/docs/queue/')
        self.assertEqual(q.status_code, 200)
        self.assertIn('received', q.json())

        card = self.client.get(f'/api/docs/entry/{reg.json()["entry"]}/')
        self.assertEqual(card.status_code, 200)
        self.assertEqual(len(card.json()['revisions']), 1)
        self.assertEqual(len(card.json()['issues']), 1)

    def test_validate_no_code_fails(self):
        r = self.client.post('/api/docs/intake/', {'email_id': self.email.pk}, content_type='application/json')
        rev = r.json()['id']
        get_p, post_p = self._mock_engine(podano_verdict='NO_CODE')
        with get_p, post_p:
            v = self.client.post(f'/api/docs/{rev}/validate/', {'code': 500}, content_type='application/json')
        self.assertEqual(v.json()['verdict'], 'FAIL')
        self.assertEqual(v.json()['status'], 'has_remarks')
        # замечание вручную
        rm = self.client.post(f'/api/docs/{rev}/remarks/', {'text': 'Нет в accdb'}, content_type='application/json')
        self.assertEqual(rm.status_code, 201)
        # выдача из has_remarks запрещена
        iss = self.client.post(f'/api/docs/{rev}/issue/', {'waybill_no': '1'}, content_type='application/json')
        self.assertEqual(iss.status_code, 400)

    def test_validate_unreachable_503(self):
        from unittest.mock import patch
        from DocRegistry import designbase_client as dbc
        r = self.client.post('/api/docs/intake/', {'email_id': self.email.pk}, content_type='application/json')
        rev = r.json()['id']
        with patch.object(dbc, 'get', side_effect=dbc.DesignBaseUnreachable('down')), \
                patch.object(dbc, 'post', side_effect=dbc.DesignBaseUnreachable('down')):
            v = self.client.post(f'/api/docs/{rev}/validate/', {'code': 500}, content_type='application/json')
        self.assertEqual(v.status_code, 503)

    def test_unauthorized(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/docs/queue/').status_code, 401)


class DocUiTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user('uiviewer', 'u@u.u', 'pw')
        self.client.force_login(self.user)
        self.entry = DocRegisterEntry.objects.create(code=501, cipher='ВВ-17-1.1-АР1')
        self.rev = DocRevision.objects.create(entry=self.entry, rev_no=1, status='has_remarks')
        self.remark = DocRemark.objects.create(revision=self.rev, text='Стены не те')
        self.issue = DocIssue.objects.create(entry=self.entry, waybill_no='301')

    def test_queue_page(self):
        r = self.client.get('/docs/queue/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ВВ-17-1.1-АР1')
        self.assertContains(r, 'Замечания')

    def test_revision_page(self):
        r = self.client.get(f'/docs/revision/{self.rev.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Стены не те')
        self.assertContains(r, '/api/docs/')

    def test_entry_page(self):
        r = self.client.get('/docs/entry/501/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Накладная №301')

    def test_remark_sheet_pdf(self):
        r = self.client.get(f'/docs/remark/{self.remark.pk}/sheet.pdf')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        content = b''.join(r.streaming_content)
        self.assertTrue(content.startswith(b'%PDF'))
        self.remark.refresh_from_db()
        self.assertTrue(self.remark.sheet_pdf.name.endswith('.pdf'))

    def test_waybill_pdf(self):
        r = self.client.get(f'/docs/issue/{self.issue.pk}/waybill.pdf')
        self.assertEqual(r.status_code, 200)
        content = b''.join(r.streaming_content)
        self.assertTrue(content.startswith(b'%PDF'))

    def test_queue_login_required(self):
        self.client.logout()
        r = self.client.get('/docs/queue/')
        self.assertEqual(r.status_code, 302)


class DocReferenceTest(TestCase):
    def setUp(self):
        from .models import DocBuilding, DocDeveloper, DocSection, DocSigner
        self.b = DocBuilding.objects.create(code=4, number='1.4', name='Коровник  № 4')
        self.s = DocSection.objects.create(code=21, short='ВК', name='Внутренние системы ВиК')
        self.d = DocDeveloper.objects.create(code=1, name='ДеЛаваль')
        DocSigner.objects.create(order=1, position='Менеджер по проектированию',
                                 company='ООО «СИМРУС»', person='Страхов С.')

    def test_entry_fk_resolution_like_accdb_row_1(self):
        e = DocRegisterEntry.objects.create(
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
        e = DocRegisterEntry.objects.create(
            code=2, cipher='ВВ-17-1.3-АПС1', section=self.s,
            building=self.b, building_no=self.b, developer=self.d)
        iss = DocIssue.objects.create(entry=e, waybill_no='305')
        r = self.client.get(f'/docs/issue/{iss.pk}/approval.pdf')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        content = b''.join(r.streaming_content)
        self.assertTrue(content.startswith(b'%PDF'))
        iss.refresh_from_db()
        self.assertTrue(iss.approval_pdf.name.endswith('.pdf'))

    def test_stamp_in_signature_cell(self):
        from .models import DocProject, DocSigner
        from .pdf_forms import approval_sheet_multi
        from .services import signers_for
        DocSigner.objects.create(order=1, position='Менеджер по проектированию',
                                 company='ООО «СИМРУС»', person='Страхов С.', stamp=True)
        m1, _ = DocProject.objects.get_or_create(code='M1', defaults={'name': 'Волоколамск'})
        e = DocRegisterEntry.objects.create(code=41, cipher='S', project=m1)
        text = self._pdf_text(approval_sheet_multi([e], signers_for()))
        self.assertIn('СОГЛАСОВАНО', text)
        self.assertIn('Страхов С.', text)

    def test_buildings_scoped_per_project(self):
        from django.db import IntegrityError
        from .models import DocBuilding, DocProject
        m1, _ = DocProject.objects.get_or_create(code='M1', defaults={'name': 'Волоколамск'})
        k1 = DocProject.objects.create(code='K1', name='Калуга')
        DocBuilding.objects.create(code=4, number='1.4', name='Коровник № 4', project=m1)
        # тот же номер у К1 — другое здание, ок (self.b из setUp без проекта не в счёт)
        DocBuilding.objects.create(code=4, number='1.4', name='Коровник № 4', project=k1)
        self.assertEqual(DocBuilding.objects.filter(code=4).exclude(project__isnull=True).count(), 2)
        # дубль внутри проекта запрещён
        with self.assertRaises(IntegrityError):
            DocBuilding.objects.create(code=4, number='1.4-дубль', project=m1)

    def test_admin_display_methods(self):
        from .admin import DocRegisterEntryAdmin
        from django.contrib import admin as dj_admin
        e = DocRegisterEntry.objects.create(
            code=3, cipher='X', section=self.s,
            building_no=self.b, building=self.b, developer=self.d)
        ma = DocRegisterEntryAdmin(DocRegisterEntry, dj_admin.site)
        self.assertEqual(ma.get_building(e), 'Коровник  № 4')
        self.assertEqual(ma.get_section(e), 'ВК')
        self.assertEqual(ma.get_building_no(e), '1.4')
        self.assertEqual(ma.get_developer(e), 'ДеЛаваль')
        e2 = DocRegisterEntry.objects.create(code=4, cipher='Y')
        self.assertEqual(ma.get_building(e2), '—')

    def test_admin_action_approval_sheet(self):
        from django.contrib.auth.models import User
        User.objects.create_superuser('boss', 'b@b.b', 'pw')
        self.client.force_login(User.objects.get(username='boss'))
        e1 = DocRegisterEntry.objects.create(
            code=11, cipher='ВВ-17-1-АР1', building=self.b, section=self.s, developer=self.d)
        e2 = DocRegisterEntry.objects.create(
            code=12, cipher='ВВ-17-2-АР1', building=self.b, section=self.s, developer=self.d)
        r = self.client.post('/admin/DocRegistry/docregisterentry/', {
            'action': 'make_approval_sheet', '_selected_action': [e1.pk, e2.pk]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_approval_multi_global_signers(self):
        from .pdf_forms import approval_sheet_multi
        from .services import signers_for
        e = DocRegisterEntry.objects.create(
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
        m1, _ = DocProject.objects.update_or_create(
            code='M1', defaults={'name': 'Волоколамск',
                                 'customer': 'ООО «ТиЭйч-РУС Милк Фуд»',
                                 'object_name': 'Комплекс МЖК',
                                 'object_address': 'Волоколамский район',
                                 'designer': 'ИП РОДИН'})
        e = DocRegisterEntry.objects.create(
            code=21, cipher='ВВ-17-9-АР1', building=self.b, project=m1)
        text = self._pdf_text(approval_sheet_multi([e], signers_for()))
        self.assertIn('Волоколамский район', text)
        self.assertIn('ИП РОДИН', text)

    def test_approval_note_tom_only_single_cipher(self):
        from .models import DocProject
        from .pdf_forms import approval_sheet_multi
        from .services import signers_for
        m1, _ = DocProject.objects.get_or_create(code='M1', defaults={'name': 'Волоколамск'})
        a = DocRegisterEntry.objects.create(code=51, cipher='ТОМ-1', project=m1)
        b = DocRegisterEntry.objects.create(code=52, cipher='ТОМ-1', project=m1)
        c = DocRegisterEntry.objects.create(code=53, cipher='', project=m1)
        self.assertIn('общий том', self._pdf_text(approval_sheet_multi([a, b], signers_for())))
        self.assertNotIn('общий том', self._pdf_text(approval_sheet_multi([a, c], signers_for())))

    def test_approval_header_multi_projects_table(self):
        from .models import DocProject
        from .pdf_forms import approval_sheet_multi
        from .services import signers_for
        m1, _ = DocProject.objects.update_or_create(
            code='M1', defaults={'name': 'Волоколамск', 'customer': 'Заказчик-М1'})
        k1 = DocProject.objects.create(code='K1', name='Калуга', customer='Заказчик-К1')
        e1 = DocRegisterEntry.objects.create(code=22, cipher='A', project=m1)
        e2 = DocRegisterEntry.objects.create(code=23, cipher='B', project=k1)
        text = self._pdf_text(approval_sheet_multi([e1, e2], signers_for()))
        self.assertIn('Волоколамск', text)
        self.assertIn('Калуга', text)
        self.assertIn('Заказчик-К1', text)

    def test_reimport_keeps_manual_k1(self):
        from .models import DocProject, DocRegisterEntry
        m1, _ = DocProject.objects.get_or_create(code='M1', defaults={'name': 'Волоколамск'})
        k1 = DocProject.objects.create(code='K1', name='Калуга')
        manual = DocRegisterEntry.objects.create(code=31, cipher='K', project=k1)
        # имитация update_or_create импорта (defaults без project) + backfill
        DocRegisterEntry.objects.update_or_create(
            code=31, defaults={'cipher': 'K-upd'})
        DocRegisterEntry.objects.filter(project__isnull=True).update(project=m1)
        manual.refresh_from_db()
        self.assertEqual(manual.project_id, 'K1')
        self.assertEqual(manual.cipher, 'K-upd')
        fresh = DocRegisterEntry.objects.create(code=32, cipher='N')
        DocRegisterEntry.objects.filter(project__isnull=True).update(project=m1)
        fresh.refresh_from_db()
        self.assertEqual(fresh.project_id, 'M1')


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
            DocRegisterEntry.objects.create(code=7, cipher='T', accdb_row_hash='h7')
            out = StringIO()
            call_command('check_accdb_drift', stdout=out)
            self.assertIn('drift OK', out.getvalue())
            DocRegisterEntry.objects.create(code=8, cipher='U', accdb_row_hash='h8')
            with self.assertRaises(CommandError):
                call_command('check_accdb_drift', stdout=StringIO())

