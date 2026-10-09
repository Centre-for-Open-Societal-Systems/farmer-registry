import copy
import re
import sys
import types
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

from bulk_import_test_support import ROOT, fi, service


def metadata():
    text = (ROOT / 'meta_data/register-metadata/g2p_register_sections.sql').read_text(encoding='utf-8')
    sections = [types.SimpleNamespace(section_id=m[1], section_register_id=m[2], section_mnemonic=m[3])
                for m in re.findall(r"\('([^']*)','([^']*)','([^']*)','[^']*','([^']*)'", text)]
    sections.append(types.SimpleNamespace(section_id='phones', section_register_id='phones', section_mnemonic='fr_farmer_phone_numbers'))
    return sections


class MappingTests(unittest.TestCase):
    def test_one_farmer_and_correct_parent_links(self):
        payload = fi.row_to_submission(fi.example_rows()[0])
        original = copy.deepcopy(payload)
        groups = service.prepare_sections(payload, metadata())
        self.assertEqual(payload, original)
        farmer = next(g['records'][0] for g in groups if g['section'].section_register_id == service.FARMER_REGISTER_ID)
        household = groups[0]['records'][0]
        self.assertEqual(groups[0]['section'].section_register_id, service.HOUSEHOLD_REGISTER_ID)
        self.assertEqual(farmer['link_internal_record_id'], household['internal_record_id'])
        self.assertEqual(farmer['birth_date'], '1985-04-12')
        self.assertEqual(farmer['import_source'], 'IMPORT_FILE')
        self.assertNotIn('phone_numbers', farmer)
        for group in groups[2:]:
            expected = household if group['section'].section_mnemonic == 'fr_household_members' else farmer
            for child in group['records']:
                self.assertEqual(child['link_internal_record_id'], expected['internal_record_id'])
        again = service.prepare_sections(payload, metadata())
        self.assertNotEqual(groups[0]['records'][0]['internal_record_id'], again[0]['records'][0]['internal_record_id'])

    def test_missing_section_is_not_silently_dropped(self):
        with self.assertRaisesRegex(fi.RowError, 'missing section'):
            service.prepare_sections(fi.row_to_submission(fi.example_rows()[0]), [])

    def test_no_household_created_without_members(self):
        groups = service.prepare_sections(fi.row_to_submission({'first_name': 'A', 'father_first_name': 'B'}), metadata())
        self.assertNotIn(service.HOUSEHOLD_REGISTER_ID, [g['section'].section_register_id for g in groups])


class TransactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_parser_save_finalize_and_commit_failures_are_isolated(self):
        committed = []
        attempts = []
        class AppError(Exception):
            pass
        module = types.ModuleType('openg2p_fastapi_common.errors.base_exception')
        module.BaseAppException = AppError
        registry_errors = types.ModuleType('openg2p_registry_core.errors')
        class RegistryError(Exception): pass
        registry_errors.G2PRegistryException = RegistryError
        class Session:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            @asynccontextmanager
            async def begin(self):
                yield
                if self.name == 'CommitError': raise RuntimeError('commit failed')
                committed.append(self.name)
        class Intake:
            async def _validate_form(self, *args): pass
            async def _get_form_sections(self, *args): return metadata()
            async def create_submission_with_session(self, **kwargs):
                assert kwargs['submission_source'] == 'STAFF_PORTAL'
                assert kwargs['created_by'] == 'staff-sub'
                return types.SimpleNamespace(submission_id=str(len(attempts)))
            async def save_intake_form_submission_with_session(self, **kwargs):
                if kwargs['section_register_id'] == service.FARMER_REGISTER_ID:
                    name = kwargs['section_payload'][0]['first_name']
                    kwargs['session'].name = name
                    attempts.append(name)
                    if name == 'SaveError': raise RegistryError('invalid row')
            async def finalize_submission_with_session(self, submission_id, session, **kwargs):
                assert kwargs['requester_sub'] == 'staff-sub'
                assert kwargs['bearer_token'] == 'token'
                if session.name == 'FinalizeError': raise AppError('workflow unavailable')
        rows = [{'first_name': name, 'father_first_name': 'B'} for name in
                ['Good', '', 'SaveError', 'FinalizeError', 'CommitError', 'Last']]
        with patch.dict(sys.modules, {module.__name__: module, registry_errors.__name__: registry_errors}), self.assertLogs(service.__name__, level='ERROR'):
            result = await service.import_rows(rows, 'form', 'staff-sub', 'staff-sub', 'token', Intake(), Session)
        self.assertEqual(committed, ['Good', 'Last'])
        self.assertEqual((result['successful'], result['failed']), (2, 4))
        self.assertEqual([r['ok'] for r in result['results']], [True, False, False, False, False, True])
        self.assertEqual([r['row'] for r in result['results']], [2, 3, 4, 5, 6, 7])
        self.assertEqual(result['results'][2]['errors'], ['invalid row'])


if __name__ == '__main__': unittest.main()
