"""JSON-safe hierarchy at the native change-request outgestion boundary.

rc.557 dumps RecordData in Python mode, leaving Decimal and temporal values in
extras. Its payload model then calls json.dumps and rolls back the approval.
Use native traversal and fanout, supplying the supported hierarchy argument;
native fanout constructs its default hierarchy directly rather than resolving
the component registry. All approval and webhook handling remain inherited.
"""

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


class OANJsonHierarchy(G2PRegisterHierarchicalService):
    async def enrich_record_hierarchy(
        self, register_definition, record, session, visited_registers=None
    ):
        result = await super().enrich_record_hierarchy(
            register_definition, record, session, visited_registers
        )
        # Pydantic's JSON semantics preserve Decimal precision as a string and
        # encode dates/UUIDs consistently, including nested extra fields.
        return to_jsonable_python(result)


class OANOutgestChangeRequestService(G2PRegisterChangeRequestService):
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
            hierarchical_service=OANJsonHierarchy.get_component(),
        )


def install_outgest_json():
    if OANJsonHierarchy.get_component() is None:
        OANJsonHierarchy()
    current = G2PRegisterChangeRequestService.get_component()
    if isinstance(current, OANOutgestChangeRequestService):
        return current
    service = OANOutgestChangeRequestService()
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
