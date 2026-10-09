"""Run inside the staff API image against a disposable, seeded database copy.

Set BULK_TEST_DATABASE and REGISTRY_STAFF_PORTAL_API_DB_DBNAME to the same
database named farmer_bulk_test_*. Disable AWE; this test checks real registry
persistence and approval/ingestion, without calling an external workflow.
"""
import asyncio
import os
from pathlib import Path

from openg2p_registry_staff_api.main import app
from openg2p_fastapi_common.context import dbengine
from openg2p_registry_core.models import G2PIntakeFormDefinition, G2PIntakeFormSubmission
from openg2p_registry_core.services import G2PIntakeFormDataService
from openg2p_registry_core.services.g2p_verification_service import G2PRegisterVerificationService
from openg2p_registry_core.schemas import AddVerificationPayload
from openg2p_registry_core.services.g2p_awe_integration_service import G2PAweIntegrationService
from openg2p_registry_farmer_extension.bulk_import import farmer_import as fi
from openg2p_registry_farmer_extension.bulk_import.service import (
    FARMER_REGISTER_ID, HOUSEHOLD_REGISTER_ID, import_rows, prepare_sections,
)
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker


async def main():
    expected = os.environ['BULK_TEST_DATABASE']
    assert expected.startswith('farmer_bulk_test_')
    assert os.environ['REGISTRY_STAFF_PORTAL_API_DB_DBNAME'] == expected
    async with app.router.lifespan_context(app):
        sessions = async_sessionmaker(dbengine.get(), expire_on_commit=False)
        intake = G2PIntakeFormDataService.get_component()
        assert not G2PAweIntegrationService.get_component()._awe_enabled()
        async with sessions() as session:
            assert (await session.execute(text('select current_database()'))).scalar_one() == expected
            form = (await session.execute(select(G2PIntakeFormDefinition).where(
                G2PIntakeFormDefinition.register_id == FARMER_REGISTER_ID))).scalars().first()
            assert form
            sections = await intake._get_form_sections(form.form_id, session)
            before = (await session.execute(select(func.count()).select_from(G2PIntakeFormSubmission))).scalar_one()

        ids = []
        for extension in ('csv', 'xlsx'):
            content = (Path(__file__).resolve().parents[1] / 'docker/staff-ui/assets' /
                       f'farmer-import-template.{extension}').read_bytes()
            good = fi.read_rows('example.' + extension, content)[0]
            # Domain failure after submission creation must roll back, not just
            # parser validation. National-ID length is enforced by the domain.
            bad = dict(good, national_fan='123')
            result = await import_rows([good, bad, dict(good)], form.form_id,
                                       'bulk-integration', 'bulk-integration', None, intake, sessions)
            print(extension, result, flush=True)
            assert (result['successful'], result['failed']) == (2, 1), result
            ids.extend(r['submission_id'] for r in result['results'] if r['ok'])
            groups = prepare_sections(fi.row_to_submission(good), sections)
            for submission_id in ids[-2:]:
                payload = await intake.get_submission_payload(submission_id)
                assert payload.draft_status == 'FINAL'
                assert payload.approval_status == 'PENDING'
                assert payload.submission_source == 'STAFF_PORTAL'
                assert payload.created_by == 'bulk-integration'
                async with sessions() as session:
                    records = {}
                    for group in groups:
                        register = group['section'].section_register_id
                        model = await intake._resolve_intake_form_class(register, session)
                        stored = await intake._get_intake_rows_list(model, submission_id, session)
                        assert len(stored) == len(group['records']), register
                        records[register] = stored
                        for actual, source in zip(stored, group['records']):
                            for key, value in source.items():
                                if key in ('internal_record_id', 'link_internal_record_id') or value is None:
                                    continue
                                actual_value = getattr(actual, key, None)
                                if hasattr(actual_value, 'isoformat'):
                                    actual_value = actual_value.isoformat()
                                # The domain intentionally normalizes phone numbers.
                                if key in ('phone_number',):
                                    continue
                                assert actual_value == value, (register, key, actual_value, value)
                    farmer = records[FARMER_REGISTER_ID][0]
                    household = records[HOUSEHOLD_REGISTER_ID][0]
                    assert farmer.link_internal_record_id == household.internal_record_id
                    for group in groups:
                        register = group['section'].section_register_id
                        if register in (FARMER_REGISTER_ID, HOUSEHOLD_REGISTER_ID):
                            continue
                        parent = household if group['section'].section_mnemonic == 'fr_household_members' else farmer
                        assert all(r.link_internal_record_id == parent.internal_record_id for r in records[register])

        async with sessions() as session:
            after = (await session.execute(select(func.count()).select_from(G2PIntakeFormSubmission))).scalar_one()
            assert after - before == 4, (before, after)

        for submission_id in ids:
            payload = await intake.get_submission_payload(submission_id)
            for number in range(payload.number_of_verifications_required):
                await G2PRegisterVerificationService.get_component().add_verification(AddVerificationPayload(
                    submission_id=submission_id, verified_by=f'bulk-test-verifier-{number}',
                    is_approved=True, verification_observations='Disposable database integration test',
                ))
            await intake.approve_submission(submission_id, 'bulk-test-approver')
            await intake.process_submission_register_ingest(submission_id)
            payload = await intake.get_submission_payload(submission_id)
            assert payload.approval_status == 'APPROVED'
            assert payload.register_ingest_process_status == 'PROCESSED'
            async with sessions() as session:
                for group in groups:
                    _, model, live_model, _, _ = await intake._resolve_submission_models(
                        group['section'].section_register_id, session)
                    rows = await intake._get_intake_rows_list(model, submission_id, session)
                    for row in rows:
                        live = await session.get(live_model, row.internal_record_id)
                        assert live is not None
                        assert getattr(live, 'link_internal_record_id', None) == getattr(row, 'link_internal_record_id', None)
        print('PASS: CSV/XLSX mixed imports, every supplied field, row rollback, approval, ingestion and parent links', flush=True)


asyncio.run(main())
