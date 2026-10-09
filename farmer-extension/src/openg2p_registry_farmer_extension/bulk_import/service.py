"""Create-only spreadsheet intake, using the same save/finalize path as staff."""

import copy
import logging
from uuid import uuid4

from .farmer_import import RowError, rows_to_submissions

FARMER_REGISTER_ID = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"
HOUSEHOLD_REGISTER_ID = "9055ab43-c85d-4833-bd00-ca657bb72644"
_logger = logging.getLogger(__name__)


def prepare_sections(payload, sections):
    """Merge sections of the same record; never use IDs supplied by a file.

    Farmer attributes span several UI sections but share ONE intake table row.
    Child tables get new IDs and an explicit link to their actual parent.
    """
    payload = copy.deepcopy(payload)
    by_name = {section.section_mnemonic: section for section in sections}
    farmer_id = str(uuid4())
    household_id = None
    if payload.get("fr_household_members"):
        household_id = str(uuid4())
        personal = payload["fr_farmer_personal_info"][0]
        is_head = payload["fr_farmer_household_lookup"][0]["is_household_head"]
        name = " ".join(personal[k] for k in ("first_name", "middle_name", "last_name") if personal.get(k))
        payload["fr_household_information"] = [{"household_head": name if is_head else None}]

    grouped = {}
    for mnemonic, records in payload.items():
        if not records:
            continue
        section = by_name.get(mnemonic)
        if section is None:
            raise RowError(f"Selected form is missing section '{mnemonic}'; update the farmer metadata")
        register = section.section_register_id
        if register not in grouped:
            grouped[register] = {"section": section, "records": []}
        target = grouped[register]["records"]
        if register in (FARMER_REGISTER_ID, HOUSEHOLD_REGISTER_ID):
            if not target:
                target.append({})
            for record in records:
                target[0].update(record)
        else:
            target.extend(records)

    for register, group in grouped.items():
        for record in group["records"]:
            if register == FARMER_REGISTER_ID:
                record["internal_record_id"] = farmer_id
                record["import_source"] = "IMPORT_FILE"
                # Phones have their own section, not an embedded person field.
                record.pop("phone_numbers", None)
                if household_id:
                    record["link_internal_record_id"] = household_id
            elif register == HOUSEHOLD_REGISTER_ID:
                record["internal_record_id"] = household_id
            else:
                record["internal_record_id"] = str(uuid4())
                record["link_internal_record_id"] = (
                    household_id if group["section"].section_mnemonic == "fr_household_members" else farmer_id
                )
            for key, value in list(record.items()):
                if value == "":
                    record[key] = None

    # Save parent records before tables. This also supports platform releases
    # that validate parent existence during each section save.
    order = {HOUSEHOLD_REGISTER_ID: 0, FARMER_REGISTER_ID: 1}
    return sorted(grouped.values(), key=lambda group: order.get(group["section"].section_register_id, 2))


async def import_rows(rows, form_id, actor, requester_sub, bearer_token, intake, session_factory):
    """One transaction per row, including finalization. No live-register writes."""
    async with session_factory() as session:
        await intake._validate_form(form_id, FARMER_REGISTER_ID, session)
        sections = await intake._get_form_sections(form_id, session)
    results = []
    from openg2p_fastapi_common.errors.base_exception import BaseAppException
    from openg2p_registry_core.errors import G2PRegistryException

    for parsed in rows_to_submissions(rows):
        result = {"row": parsed["row"], "ok": False}
        if not parsed["ok"]:
            result["errors"] = parsed["errors"]
            results.append(result)
            continue
        try:
            groups = prepare_sections(parsed["submission"], sections)
            async with session_factory() as session:
                async with session.begin():
                    submission = await intake.create_submission_with_session(
                        form_id=form_id, register_id=FARMER_REGISTER_ID,
                        submission_source="STAFF_PORTAL", partner_id=None,
                        section_payloads=None, created_by=actor, session=session,
                    )
                    for group in groups:
                        section = group["section"]
                        await intake.save_intake_form_submission_with_session(
                            submission_id=submission.submission_id,
                            section_id=section.section_id,
                            section_payload=group["records"],
                            section_register_id=section.section_register_id,
                            form_id=form_id, register_id=FARMER_REGISTER_ID,
                            created_by=actor, session=session,
                        )
                    await intake.finalize_submission_with_session(
                        submission.submission_id, session,
                        bearer_token=bearer_token, requester_sub=requester_sub,
                    )
                    submission_id = str(submission.submission_id)
            # A successful finalize is not sufficient: the commit must succeed.
            result.update(ok=True, submission_id=submission_id)
        except (RowError, BaseAppException, G2PRegistryException) as error:
            result["errors"] = [getattr(error, "message", None) or str(error)]
        except Exception:
            _logger.exception("Farmer bulk import failed at row %s", parsed["row"])
            result["errors"] = ["The submission could not be completed. Check intake submissions before retrying this row."]
        results.append(result)
    successful = sum(row["ok"] for row in results)
    return {"total": len(results), "successful": successful, "failed": len(results) - successful, "results": results}
