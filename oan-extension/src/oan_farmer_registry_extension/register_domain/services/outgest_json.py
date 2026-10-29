"""JSON-safe hierarchy at both native outgestion boundaries.

rc.557 dumps RecordData in Python mode, leaving Decimal and temporal values in
extras. Its payload model then calls json.dumps and rolls back the approval
(change requests) or fails the register ingest of an approved intake form.
Use native traversal and fanout, supplying the supported hierarchy argument;
native fanout constructs its default hierarchy directly rather than resolving
the component registry. All approval and webhook handling remain inherited.

The intake path lives in the celery worker's ingest task, which binds the
native fanout by name and builds its own hierarchy service. The worker module
is given a fanout that supplies the JSON-safe hierarchy instead; the task and
its arguments are untouched.
"""
import importlib
import logging

_logger = logging.getLogger(__name__)
INGEST_WORKER_MODULE = (
    "openg2p_registry_celery_worker.tasks.intake_form_register_ingest_worker"
)

from openg2p_fastapi_common.context import component_registry
from openg2p_registry_core.services.g2p_outgest_fanout_service import (
    fanout_outgest_rows,
)
from openg2p_registry_core.services.g2p_register_change_request_service import (
    G2PRegisterChangeRequestService,
)
from openg2p_registry_core.services.g2p_register_hierarchical_service import (
    G2PRegisterHierarchicalService,
)
from pydantic_core import to_jsonable_python

# Absolute: tests load this file by path, with no parent package.
from oan_farmer_registry_extension.register_domain.services.direct_approval import DirectApprovalClosed


class JsonSafeHierarchyService(G2PRegisterHierarchicalService):
    async def enrich_record_hierarchy(
        self, register_definition, record, session, visited_registers=None
    ):
        result = await super().enrich_record_hierarchy(
            register_definition, record, session, visited_registers
        )
        # Pydantic's JSON semantics preserve Decimal precision as a string and
        # encode dates/UUIDs consistently, including nested extra fields.
        return to_jsonable_python(result)


class JsonSafeOutgestChangeRequestService(DirectApprovalClosed, G2PRegisterChangeRequestService):
    async def _fanout_outgest_for_change_request(self, change_request, session):
        definition, register_class, _ = await self._get_register_class_and_schema(
            change_request.register_id, session
        )
        row = await self._get_existing_record(
            register_class, change_request.internal_record_id, session
        )
        if row is None:
            return
        await fanout_outgest_rows(
            definition,
            row,
            session,
            change_request_id=change_request.change_request_id,
            changed_by=change_request.created_by,
            changed_at=change_request.created_at,
            approved_by=change_request.approved_by,
            approved_at=change_request.approved_at,
            changed_by_partner_id=change_request.source_partner_id,
            hierarchical_service=JsonSafeHierarchyService.get_component(),
        )


async def fanout_outgest_rows_json(*args, **kwargs):
    """Native fanout with the JSON-safe hierarchy, whatever the caller built."""
    kwargs["hierarchical_service"] = JsonSafeHierarchyService.get_component()
    return await fanout_outgest_rows(*args, **kwargs)


def install_intake_outgest_json(module_name=INGEST_WORKER_MODULE):
    """Bind the JSON-safe fanout into the worker's intake ingest task.

    Only worker and beat carry the celery worker package; the API processes
    have no ingest task to adjust.
    """
    try:
        worker = importlib.import_module(module_name)
    except ImportError:
        return None
    if getattr(worker, "fanout_outgest_rows", None) is fanout_outgest_rows_json:
        return worker
    if not callable(getattr(worker, "fanout_outgest_rows", None)):
        _logger.warning("%s has no fanout_outgest_rows to replace", module_name)
        return None
    worker.fanout_outgest_rows = fanout_outgest_rows_json
    return worker


def install_outgest_json():
    if JsonSafeHierarchyService.get_component() is None:
        JsonSafeHierarchyService()
    install_intake_outgest_json()
    current = G2PRegisterChangeRequestService.get_component()
    if isinstance(current, JsonSafeOutgestChangeRequestService):
        return current
    service = JsonSafeOutgestChangeRequestService()
    component_registry.remove(service)
    first = next(
        (
            i
            for i, c in enumerate(component_registry)
            if isinstance(c, G2PRegisterChangeRequestService)
        ),
        len(component_registry),
    )
    component_registry.insert(first, service)
    return service
