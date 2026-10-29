"""The household on a farmer's intake form, checked when the form is finalized.

A new farmer's household is either one already registered, picked in the
household lookup (the farmer's link_internal_record_id), or a new one, entered
in the household sections of the same form; the household is then created with
the farmer on approval. The per-section hooks only see the section being saved,
so the whole form is checked at finalize, the way the farmer extension checks a
household's own intake form (household_submission_validation): exactly one of
the two, and a new household's members by the farmer extension's roster rules.

A household's head is the household's own attribute, so a farmer form never
changes a registered household: answering Yes to Household Head is accepted
only when that household already names the farmer as its head and no other
farmer of it is its head. Otherwise the message says which change request to
raise first. Nothing reaches a register without its own approval.
"""

from openg2p_registry_farmer_extension.openg2p_farmer.register_domain.services import (
    G2PFarmerIntakeFormDataService,
)
from openg2p_registry_farmer_extension.openg2p_farmer.register_domain.services.domain_validation_utils import (
    as_bool,
    is_blank,
    validation_error,
)
from openg2p_registry_farmer_extension.openg2p_farmer.register_domain.services.household_submission_validation import (
    validate_household_roster,
)
from sqlalchemy import select

from .direct_approval import DirectApprovalClosed
from .required_intake import RequiredFieldsMixin

FARMER_REGISTER_MNEMONIC = "Farmer"

MESSAGES = {
    "household_both": (
        "Household: an existing household is picked in the household lookup and a new household is "
        "entered as well. Keep one: clear the household lookup to register the new household, or clear "
        "the household information and members to join the picked one."
    ),
    "household_none": (
        "Household: none is given. Pick the farmer's household in the household lookup, or enter a new "
        "household in the household information and members."
    ),
}


def _say(messages: dict, key: str) -> str:
    return messages.get(key) or MESSAGES[key]


def _get(row, key: str):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def _same_name(a, b) -> bool:
    return " ".join(str(a or "").split()).casefold() == " ".join(str(b or "").split()).casefold()


def farmer_name(farmer) -> str:
    return " ".join(
        str(_get(farmer, key)).strip() for key in ("first_name", "middle_name", "last_name")
        if not is_blank(_get(farmer, key))
    )


def household_head_problems(name: str, household, other_heads: list[str]) -> list[str]:
    """A farmer answered Yes to Household Head for a registered household."""
    number = _get(household, "functional_record_id") or "the picked household"
    head = _get(household, "household_head")
    problems = []
    if not _same_name(head, name):
        problems.append(
            f"Household Head: the farmer is marked as the head of {number}, whose registered head is "
            f"{head or 'not set'}. A household's head changes only through a change request on that household: "
            f"raise one on its Household Information making {name or 'this farmer'} the head, and submit this "
            "again once it is approved. Or answer No to Household Head"
        )
    problems.extend(
        f"Household Head: {other} is already the head of {number}. Raise a change request on {other}'s record "
        "answering No to Household Head, and submit this again once it is approved. Or answer No to Household Head"
        for other in other_heads
    )
    return problems


def new_household_head_problems(farmers: list, household) -> list[str]:
    """The head of a household entered on the form, set from the farmer who is
    its head, so the approver sees the household as it will be registered."""
    heads = [f for f in farmers if as_bool(_get(f, "is_household_head"))]
    if household is None or not heads:
        return []
    name = farmer_name(heads[0])
    typed = _get(household, "household_head")
    if is_blank(typed):
        if isinstance(household, dict):
            household["household_head"] = name
        else:
            household.household_head = name
        return []
    if _same_name(typed, name):
        return []
    return [(
        f"Household Head: the farmer is marked as the head, and the household information names {typed} as "
        f"its head. Enter {name or 'the farmer'} as the household's head, or answer No to Household Head"
    )]


async def registered_household_head_problems(session, farmer, household_id, name: str) -> list[str]:
    from openg2p_registry_extensions.register_domain.models import (
        G2PRegisterFarmer,
        G2PRegisterHousehold,
    )

    household = await session.get(G2PRegisterHousehold, household_id) if household_id else None
    if household is None:
        return []
    others = (await session.execute(
        select(G2PRegisterFarmer.record_name).where(
            G2PRegisterFarmer.link_internal_record_id == household_id,
            G2PRegisterFarmer.internal_record_id != str(_get(farmer, "internal_record_id") or ""),
            G2PRegisterFarmer.is_household_head.is_(True),
            G2PRegisterFarmer.record_status == "ACTIVE",
        )
    )).scalars().all()
    return household_head_problems(name, household, [o or "another farmer" for o in others])


def check_farmer_household(farmers: list, household, members: list, messages: dict | None = None) -> None:
    """Exactly one household for the farmer; a new one with a valid roster.

    `farmers`, `household` and `members` may be ORM rows or plain dicts.
    Raises the platform validation error on the first breach.
    """
    messages = messages or {}
    new_id = _get(household, "internal_record_id") if household is not None else None
    picked = [
        link for link in (_get(farmer, "link_internal_record_id") for farmer in farmers)
        if not is_blank(link) and link != new_id
    ]
    if household is None:
        if not picked and not members:
            validation_error(_say(messages, "household_none"))
        if not picked:
            # Members without the household information: upstream's roster
            # check says the information is missing.
            validate_household_roster(None, members)
        return
    if picked:
        validation_error(_say(messages, "household_both"))
    validate_household_roster(household, members)


class HouseholdCheckedIntakeFormDataService(
    RequiredFieldsMixin, DirectApprovalClosed, G2PFarmerIntakeFormDataService
):
    """The farmer extension's intake service, with the farmer household check
    and the required fields of every section (required_intake.py)."""

    # A farmer who picked a registered household does not enter one: the
    # household sections of the form are left empty.
    picked_parent_skips = {FARMER_REGISTER_MNEMONIC: frozenset({"Household", "HouseholdMember"})}

    async def finalize_submission_with_session(self, submission_id: str, session, *args, **kwargs):
        submission = await self._get_submission_or_error(submission_id, session)
        register_definition = await self._get_register_definition(submission.register_id, session)
        if getattr(register_definition, "register_mnemonic", None) == FARMER_REGISTER_MNEMONIC:
            await check_farmer_submission(submission.submission_id, session, submission=submission)
        if not args and kwargs.get("bearer_token") is None:
            # The ingestion worker finalizes without a user; its own client
            # token starts the approval workflow (odk/worker_token.py).
            from ...odk.worker_token import service_token

            token = await service_token()
            if token:
                kwargs["bearer_token"] = token
        return await super().finalize_submission_with_session(submission_id, session, *args, **kwargs)

    # The ingestion worker creates ODK intakes as "system"; record the ODK
    # collector instead (odk/actor.py). Every other caller is unchanged.
    async def create_submission_with_session(self, *args, **kwargs):
        if "created_by" in kwargs:
            from ...odk.actor import ingest_actor

            kwargs["created_by"] = await ingest_actor(kwargs.get("session"), kwargs["created_by"])
        return await super().create_submission_with_session(*args, **kwargs)

    async def save_intake_form_submission_with_session(
        self, submission_id, section_id, section_payload, section_register_id,
        form_id, register_id, created_by, session, documents=None,
    ):
        from copy import deepcopy

        from openg2p_registry_core.schemas.file_payload import DocumentAttachment

        from ...odk.actor import ingest_actor

        created_by = await ingest_actor(session, created_by)
        section = await self._get_section_or_error(section_id, session)
        payload = deepcopy(section_payload)
        attachments = {}
        for record in payload:
            # Native worker merges root-register sections; metadata for other
            # sections may therefore travel with this row. Bind only this
            # section's documents, never erase/attach another section's files.
            scoped = record.pop("oan_documents", {})
            for label, document_id in scoped.get(section.section_mnemonic, {}).items():
                attachments[label] = document_id
        if attachments:
            documents = list(documents or []) + [DocumentAttachment(document_id=document_id, label=label)
                for label, document_id in attachments.items()]
        from .intake_context import current_intake

        token = current_intake.set((session, submission_id))
        try:
            return await super().save_intake_form_submission_with_session(
                submission_id, section_id, payload, section_register_id, form_id,
                register_id, created_by, session, documents=documents)
        finally:
            current_intake.reset(token)

async def check_farmer_submission(submission_id: str, session, submission=None) -> None:
    # Lazy: the models import the services package when they load.
    from openg2p_registry_extensions.register_domain.models import (
        G2PIntakeFormFarmer,
        G2PIntakeFormHousehold,
        G2PIntakeFormHouseholdMember,
    )

    from . import _load, _reworded

    async def rows(cls):
        result = await session.execute(select(cls).where(cls.submission_id == str(submission_id)))
        return list(result.scalars().all())

    farmers = await rows(G2PIntakeFormFarmer)
    households = await rows(G2PIntakeFormHousehold)
    members = await rows(G2PIntakeFormHouseholdMember)
    _, _, messages = await _load()
    if submission is not None:
        # The Fayda ID against other farmers (form_integrity.py) and the head
        # of the household, in one message. The required fields of every
        # section are checked before this (required_intake.py).
        from .form_integrity import check_fayda_id_unique
        from .widget_rules import _Say

        farmer = farmers[0] if farmers else None
        problems = []
        if farmer is not None:
            label = _Say(messages).label("foundational_id", "foundational_id")
            held = await check_fayda_id_unique(farmer, label, session, messages, submission_id=submission_id)
            if held:
                problems.append(held)
        if farmer is not None and as_bool(farmer.is_household_head):
            household = households[0] if households else None
            if household is not None and farmer.link_internal_record_id in (None, "", household.internal_record_id):
                problems.extend(new_household_head_problems(farmers, household))
            else:
                problems.extend(await registered_household_head_problems(
                    session, farmer, farmer.link_internal_record_id, farmer_name(farmer)))
        if problems:
            validation_error("; ".join(problems))
    async with _reworded(messages):
        check_farmer_household(farmers, households[0] if households else None, members, messages)


def install_farmer_household_check() -> HouseholdCheckedIntakeFormDataService:
    """Put the household-checked intake service ahead of every other one: get_component()
    returns the first registered instance (the farmer extension does the same)."""
    from openg2p_fastapi_common.context import component_registry
    from openg2p_registry_core.services.intake_form_data_service import (
        G2PIntakeFormDataService,
    )

    current = G2PIntakeFormDataService.get_component()
    if isinstance(current, HouseholdCheckedIntakeFormDataService):
        return current
    service = HouseholdCheckedIntakeFormDataService()
    component_registry.remove(service)
    first = next((i for i, c in enumerate(component_registry) if isinstance(c, G2PIntakeFormDataService)),
                 len(component_registry))
    component_registry.insert(first, service)
    return service
