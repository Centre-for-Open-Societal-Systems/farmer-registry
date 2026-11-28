"""Keep parent validation inside the native intake transaction.

The upstream domain validator opens another session and cannot see lands just
saved by the worker. Native intake parent validation remains authoritative;
this scope also checks explicit links before delegating all other domain rules.
Change requests and normal domain validation retain the upstream path.
"""
from contextvars import ContextVar

from openg2p_registry_oan_farmer_extension.register_domain.services.domain_validation_utils import validation_error

current_intake = ContextVar("oan_current_intake", default=None)


# The child registers whose rows name a land, as the form titles them.
ROW_NAMES = {"Crop": "Crop records", "Livestock": "Livestock records", "FarmInputs": "Farm input records"}


async def validation_records(records, mnemonic):
    scope = current_intake.get()
    if scope is None or mnemonic not in ("Crop", "Livestock", "FarmInputs"):
        return records
    from ..models import G2PIntakeFormLand, G2PRegisterLand

    session, submission_id = scope
    normalized = []
    for record in records:
        candidate = dict(record)
        link = candidate.pop("link_internal_record_id", None)
        if link:
            intake_land = await session.get(G2PIntakeFormLand, (submission_id, str(link)))
            registered_land = None if intake_land else await session.get(G2PRegisterLand, str(link))
            if not ((intake_land and intake_land.submission_id == submission_id) or registered_land):
                validation_error(f"{ROW_NAMES[mnemonic]}: a row's plot is not a land on this form or an approved "
                                 "registered land. Pick the plot again in each row.")
        normalized.append(candidate)
    return normalized
