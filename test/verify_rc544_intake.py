"""Run in a built staff-api container against a disposable restored *_test DB.

Exercises real models and intake services, including save/read-back and policy
filtering. Unlike /ping, these calls expose errors returned in HTTP-200 envelopes.
"""
import asyncio
import inspect
import logging
import os
import sys
from unittest.mock import patch

READ_ONLY = '--read-only' in sys.argv
assert READ_ONLY or os.environ.get('REGISTRY_STAFF_PORTAL_API_DB_DBNAME', '').endswith('_test'), (
    'This test creates a draft: point it at a disposable *_test database'
)
logging.disable(logging.CRITICAL)
import openg2p_registry_staff_api.main  # Initialize the real extension and services.
from openg2p_fastapi_common.context import get_async_session_maker
from openg2p_registry_core.services.intake_form_data_service import G2PIntakeFormDataService
from openg2p_registry_extensions.register_domain import models
from sqlalchemy import select, false


async def main():
    service = G2PIntakeFormDataService.get_component()
    assert not inspect.iscoroutinefunction(service._build_intake_policy_condition)
    assert service._build_intake_policy_condition('test', None, None, None) is None
    print('PASS: intake policy helper returns a SQL condition synchronously')

    tables = {cls.__table__.name: cls for cls in vars(models).values()
              if isinstance(cls, type) and hasattr(cls, '__table__')}
    async with get_async_session_maker()() as session:
        for cls in tables.values():
            (await session.execute(select(cls).limit(1))).scalars().all()
    print(f'PASS: ORM reads all {len(tables)} domain tables without type errors')

    register = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd'
    if not READ_ONLY:
        saved = await service.save_intake_form_submission(
            submission_id=None,
            section_id='farmer_household_lookup_section_01',
            section_payload=[{'edit_action': 'ADD', 'is_household_head': False}],
            section_register_id=register,
            form_id='a1a4d25a-1cd4-4356-abac-8782382649',
            register_id=register,
            created_by='rc544-upgrade-test',
        )
        assert saved.submission_id
        readback = await service.get_submission_payload(saved.submission_id)
        records = [r for section in readback.section_payloads for r in section.records]
        assert any(r.get('is_household_head') is False for r in records)
        print('PASS: Household section saves and reads back its No selection')

    results, total = await service.search_submissions(register, None, 1, 10)
    assert total > 0 and results
    print('PASS: intake listing/search returns saved submissions')

    # A policy that denies all rows must still restrict the SQL query. Stubbing
    # only policy parsing keeps the real query execution and filtering intact.
    module = 'openg2p_registry_core.services.intake_form_data_service'
    with patch(module + '.DataPolicyHelper.resolve_register_record_policy', return_value={'test': True}), \
         patch(module + '.RegisterRecordRepository.build_policy_condition', return_value=false()):
        results, total = await service.search_submissions(register, None, 1, 10, data_policies=[{'test': True}])
        assert total == 0 and results == []
    print('PASS: intake data policy still excludes unauthorized records')


asyncio.run(main())
