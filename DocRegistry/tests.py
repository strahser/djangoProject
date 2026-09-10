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
        e = DocRegisterEntry.objects.create(code=379, cipher='ВВ-17-5.24-КЖ1', building_name='Площадка буртования')
        self.assertEqual(str(e), '379: ВВ-17-5.24-КЖ1')
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
