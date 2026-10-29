"""Required fields, enforced on the server for every registry's intake form.

The staff UI marks a field required from the section metadata
(`widget-required`, or a `require` rule that matches), but it saves a section
with "Next" as a draft with the required checks off, and "Submit" checks only
in the browser. The platform checks coded values on save and nothing on
finalize, so an API client, a stale tab or a skipped section reached approval
incomplete. `RequiredFieldsMixin` closes that, from the same metadata and with
the UI's own show/hide/require evaluation (form_integrity.py):

- Next (a section saved by a person or an API client): the section's required
  fields must be filled, and a list section whose table is required must hold
  a row. The message names each missing field by its label.
- Submit (finalize): every section of the form, over every register it
  holds, as `required_problems`.
- The ingestion worker (ODK, partners) saves whatever the source holds and
  finalizes without a person: a form missing required fields is left
  un-submitted as a draft with the reason in its remarks, so staff complete it,
  instead of failing the worker task again and again.

The mixin goes first in the farmer extension's intake service class, the one
registered as the intake form data service (household_intake.py); there is no
second registration.
"""

import contextvars
import logging
from datetime import datetime

from openg2p_registry_farmer_extension.openg2p_farmer.register_domain.services.domain_validation_utils import (
    validation_error,
)

from .form_integrity import (
    OPTIONAL_HOUSEHOLD_REGISTERS,
    _Messages,
    _blank,
    _plain,
    check_form_complete,
    condition_registers,
    intake_rows,
    required_problems,
    saved_document_labels,
)

_logger = logging.getLogger("oan-required-fields")

# Set around a save made by the ingestion worker (household_intake.py): its
# source is checked at finalize, where the form is whole.
unattended = contextvars.ContextVar("oan_unattended_save", default=False)

# Row keys that are not answers.
_TECHNICAL = {"internal_record_id", "link_internal_record_id", "edit_action", "submission_id", "record_status"}


def holds_answers(record: dict) -> bool:
    return any(not _blank(value) for key, value in record.items() if key not in _TECHNICAL)


class RequiredFieldsMixin:
    async def _messages(self) -> dict:
        from . import _load

        return (await _load())[2]

    async def refuse_missing_on_save(
        self, submission_id, section_id, section_payload, section_register_id, documents, session
    ) -> None:
        """Raise the platform validation error naming the section's required
        fields that are empty, as the staff UI evaluates them."""
        section = await self._get_section_or_error(section_id, session)
        surviving = [dict(r) for r in (section_payload or []) if (r or {}).get("edit_action") != "DELETE"]
        schema = section.section_ui_schema or {}
        existing = {}
        if submission_id:
            intake_class = await self._resolve_intake_form_class(section_register_id, session)
            existing = await self._get_intake_rows(intake_class, submission_id, session)
        records = []
        for record in surviving:
            base = _plain(existing[record["internal_record_id"]]) if record.get("internal_record_id") in existing else {}
            records.append({**base, **record})
        if not section.is_list and not records and existing:
            records = [_plain(next(iter(existing.values())))]
        rows = {section_register_id: records}
        if submission_id:
            for register_id in condition_registers(schema) - {section_register_id}:
                rows[register_id] = await intake_rows(register_id, submission_id, session)
        optional = await self._optional_register_ids(session)
        if section_register_id in optional and not any(holds_answers(r) for r in records):
            return
        if documents is None:
            saved = await saved_document_labels(submission_id, session) if submission_id else {}
            labels = saved.get(section_id, set())
        else:
            labels = {d.label for d in documents}
        problems = required_problems(
            [{"section_id": section_id, "title": schema.get("section-title"), "schema": schema,
              "register_id": section_register_id, "is_list": bool(section.is_list)}],
            rows, {section_id: labels}, await self._messages(), saving=True)
        if problems:
            validation_error("; ".join(problems))

    async def _optional_register_ids(self, session) -> list[str]:
        from openg2p_registry_core.models import G2PRegisterDefinition
        from sqlalchemy import select

        result = await session.execute(
            select(G2PRegisterDefinition.register_id).where(
                G2PRegisterDefinition.register_mnemonic.in_(OPTIONAL_HOUSEHOLD_REGISTERS)))
        return list(result.scalars().all())

    async def required_problems_for(self, submission, session) -> list[str]:
        """What the submission's whole form lacks (empty when complete)."""
        return await check_form_complete(submission, session, await self._messages())

    async def route_to_review(self, submission, problems: list[str], session):
        """Leave an ingested form un-submitted, with the reason in its
        remarks, for staff to complete and submit."""
        reason = _Messages(await self._messages())("review_reason", problems=" ".join(
            p if p.endswith(".") else p + "." for p in problems))
        submission.remarks = reason
        submission.last_updated_at = datetime.now()
        session.add(submission)
        await session.flush()
        _logger.warning("Submission %s left as a draft for review: %s", submission.submission_id, reason)
        return submission

    async def save_intake_form_submission_with_session(
        self, submission_id, section_id, section_payload, section_register_id,
        form_id, register_id, created_by, session, documents=None,
    ):
        if not unattended.get():
            await self.refuse_missing_on_save(
                submission_id, section_id, section_payload, section_register_id, documents, session)
        return await super().save_intake_form_submission_with_session(
            submission_id, section_id, section_payload, section_register_id, form_id,
            register_id, created_by, session, documents=documents)
