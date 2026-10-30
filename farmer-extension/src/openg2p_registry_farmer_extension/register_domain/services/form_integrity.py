"""A farmer's intake form, checked as a whole before it is submitted.

Two gaps the per-section checks leave open:

- Submit saves only the section that is open, then finalizes, and core's
  finalize checks only the approval and verification counts. A section never
  opened is never saved, so its required fields are never checked: the form
  could reach approval with no location, gender or ID document. Here every
  section of the form is evaluated against what the submission holds, the way
  the staff UI evaluates it (ui-widgets `evaluateWidgetConditions`): rules in
  order, the last show/hide wins, and a field is required when it is
  `widget-required` or a `require` rule matches. A hidden field is never
  required. This covers every register of the form (membership and household
  information as much as the farmer's own record) and a required list section's
  "at least one row"; required_fields.py applies it on a section's Next too.
- Duplicate matching uses names and birth date, never the Fayda ID, so the
  same FIN or FAN could be registered for a second farmer. An ID already held
  by a register record, or by another submitted form waiting for approval, is
  refused on section save and at submit, naming who holds it.

Approval stays the control: nothing here asks for a Fayda verification.

The functions above `form_sections` have no database or framework
imports, so they can be tested alone.
"""

from collections.abc import Iterable

from .widget_rules import _Say

MESSAGES = {
    "form_missing": "{section}: {label} is required. Open {section}, fill it in and save, then submit again.",
    "form_document_missing": (
        "{section}: {label} is required. Open {section}, add the file and save, then submit again."
    ),
    "save_missing": "{section}: {label} is required. Fill it in before pressing Next.",
    "save_document_missing": "{section}: {label} is required. Add the file before pressing Next.",
    "save_list_missing": "{section}: at least one entry is required. Add one before pressing Next.",
    "form_list_missing": (
        "{section}: at least one entry is required. Open {section}, add one and save, then submit again."
    ),
    "review_reason": (
        "Not submitted: required information is missing. {problems} Open the draft, complete it and submit."
    ),
    "review_reason_refused": (
        "Not submitted: some answers were not accepted. {problems} A section with an answer that was not "
        "accepted was not saved. Open the draft, enter or correct those answers and submit."
    ),
    "fayda_fin_registered": (
        "{label}: {fin} is already registered to {name} ({record}). Open that record instead of "
        "registering the farmer again; if the ID was mistyped, correct it."
    ),
    "fayda_fin_pending": (
        "{label}: {fin} is already in another submitted form, for {name} ({record}), waiting for approval. "
        "Do not register the farmer twice: wait for that decision, or ask the approver to reject it first."
    ),
}

# Widgets whose value is not a field of the section's record, or that other
# checks own: tables are their own registers, a lookup picks a household (the
# household check), display and group widgets hold no input.
_SKIPPED = {"table", "dialog-table", "register-lookup", "parent-lookup", "display", "header-section"}


class _Messages(_Say):
    def __call__(self, key: str, **params) -> str:
        template = self.text(key, MESSAGES.get(key, key))
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            return MESSAGES[key].format(**params)


def _widgets(node):
    if isinstance(node, dict):
        if "widget" in node and "widget-id" in node:
            yield node
        for value in node.values():
            yield from _widgets(value)
    elif isinstance(node, list):
        for item in node:
            yield from _widgets(item)


def value_at(values: dict, path: str | None):
    """`path` is "<register id>.<field>[.<key>...]"; `values` maps register
    ids to records (dicts)."""
    if not isinstance(path, str):
        return None
    current = values
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _boolean_like(value) -> bool:
    if value is True or value == 1:
        return True
    if value is False or value == 0:
        return False
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return bool(value)


def _blank(value) -> bool:
    return value is None or value == "" or (isinstance(value, str) and not value.strip()) \
        or (isinstance(value, list | dict) and not value)


def condition_matches(condition: dict, values: dict) -> bool:
    """ui-widgets `evaluateCondition`, operator for operator."""
    field = value_at(values, condition.get("field"))
    operator, expected = condition.get("operator"), condition.get("value")
    if operator == "equals":
        if isinstance(expected, bool):
            return isinstance(field, bool) and field == expected
        if isinstance(field, bool):
            return field == _boolean_like(expected)
        return field == expected
    if operator == "notEquals":
        return field != expected
    if operator == "notEmpty":
        return field is not None and field != ""
    if operator in ("empty", "isEmpty"):
        return field is None or field == ""
    if operator in ("greaterThan", "lessThan"):
        try:
            left, right = float(field), float(expected)
        except (TypeError, ValueError):
            return False
        return left > right if operator == "greaterThan" else left < right
    if operator in ("contains", "notContains"):
        if isinstance(field, str) and isinstance(expected, str) or isinstance(field, list):
            found = expected in field
        else:
            found = False
        return found if operator == "contains" else not found
    return False


def _rules(options) -> list[dict]:
    if not isinstance(options, dict):
        return []
    actions = options.get("actions")
    if isinstance(actions, list) and actions:
        return [a for a in actions if isinstance(a, dict) and a.get("action")]
    if options.get("action") and options.get("condition"):
        return [{"action": options["action"], "condition": options["condition"]}]
    return []


def widget_state(widget: dict, values: dict) -> tuple[bool, bool]:
    """(visible, required), as ui-widgets `evaluateWidgetConditions`."""
    base = widget.get("widget-required") is True
    visible, required = True, base
    for rule in _rules(widget.get("widget-data-options")):
        condition = rule.get("condition")
        if not isinstance(condition, dict):
            continue
        match = condition_matches(condition, values)
        if rule["action"] == "show":
            visible = match
        elif rule["action"] == "hide":
            visible = not match
        elif rule["action"] == "require":
            required = base or match
    return visible, required


def _value_path(widget: dict) -> str | None:
    path = widget.get("widget-data-path")
    if isinstance(path, dict):
        path = path.get("value")
    return path if isinstance(path, str) else None


def _section_problems(section, register_id, values, documents, say, keys) -> list[str]:
    """The required single-record fields of one section; only widgets of
    `register_id` are looked at (another register's fields are checked with
    that register's own section)."""
    missing_key, document_key = keys
    title = say.text(section.get("title"), section.get("title") or section.get("section_id") or "")
    problems: list[str] = []
    for widget in _widgets(section.get("schema") or {}):
        if widget.get("widget") in _SKIPPED:
            continue
        path = _value_path(widget)
        if not path or path.split(".", 1)[0] != register_id:
            continue
        visible, required = widget_state(widget, values)
        if not (visible and required):
            continue
        field = path.split(".")[-1]
        label = say.label(widget.get("widget-label"), field)
        if widget.get("widget") == "file":
            # A document category names itself by its title (DocumentsWidget).
            title_key = (widget.get("widget-data-options") or {}).get("title")
            if title_key:
                label = say.label(title_key, field)
            saved = documents.get(section.get("section_id"), set())
            if not ({widget.get("widget-label"), field, widget.get("widget-id")} & saved):
                problems.append(say(document_key, section=title, label=label))
        elif _blank(value_at(values, path)):
            problems.append(say(missing_key, section=title, label=label))
    return problems


def missing_required(
    sections: Iterable[dict],
    register_id: str,
    values: dict,
    documents: dict[str, set[str]],
    messages: dict | None = None,
) -> list[str]:
    """One sentence per required field of the form that the submission lacks.

    `sections` are {section_id, title, schema} in form order; only widgets of
    `register_id` are checked (another register's sections, such as the new
    household's, have their own check). `documents` maps a section id to the
    labels of the files saved in it.
    """
    say = _Messages(messages or {})
    problems: list[str] = []
    for section in sections:
        problems += _section_problems(
            section, register_id, values, documents, say, ("form_missing", "form_document_missing"))
    return list(dict.fromkeys(problems))


def section_fields(schema, register_id: str) -> set[str]:
    """The fields of `register_id` that a section's widgets write (a geo
    widget writes its value and its hierarchy). Read-only, group and skipped
    widgets write nothing, and a row's internal_record_id is never one: the
    worker merges a register's rows by it."""
    found: set[str] = set()
    for widget in _widgets(schema or {}):
        if widget.get("widget-readonly") or widget.get("widget") in _SKIPPED | {"group", "id-authentication"}:
            continue
        path = widget.get("widget-data-path")
        for value in (path.values() if isinstance(path, dict) else [path]):
            if isinstance(value, str) and value.startswith(register_id + "."):
                found.add(value.split(".", 1)[1])
    found.discard("internal_record_id")
    return found


def condition_registers(schema) -> set[str]:
    """The register ids a section's show/hide/require conditions read, so a
    save can look the other registers' values up."""
    found: set[str] = set()
    for widget in _widgets(schema or {}):
        for rule in _rules(widget.get("widget-data-options")):
            condition = rule.get("condition")
            field = condition.get("field") if isinstance(condition, dict) else None
            if isinstance(field, str) and "." in field:
                found.add(field.split(".", 1)[0])
    return found


_TABLES = {"table", "dialog-table"}


def _table_widget(schema) -> dict | None:
    return next((w for w in _widgets(schema or {}) if w.get("widget") in _TABLES), None)


def required_problems(
    sections: Iterable[dict],
    rows: dict[str, list],
    documents: dict[str, set[str]],
    messages: dict | None = None,
    *,
    saving: bool = False,
    optional_registers: Iterable[str] = (),
) -> list[str]:
    """One sentence per required field or section the submission lacks, over
    every register of the form: the single record of each one-record section,
    and "at least one row" of a list section whose table is `widget-required`.

    `sections` are {section_id, title, schema, register_id, is_list} in form
    order; `rows` maps a register id to the records the submission holds for
    it (dicts or rows); `documents` maps a section id to the labels of the
    files saved in it. `metadata` is the only source: what is required, and
    when, is what the staff UI evaluates. A register in `optional_registers`
    is checked only once the submission holds a record of it (a new household
    on a farmer's form is an alternative to picking a registered one).
    `saving` words the sentences for a section's Next button instead of Submit.
    """
    say = _Messages(messages or {})
    keys = ("save_missing", "save_document_missing") if saving else ("form_missing", "form_document_missing")
    list_key = "save_list_missing" if saving else "form_list_missing"
    optional = set(optional_registers)
    values = {register: _plain(records[0]) if records else {} for register, records in rows.items()}
    problems: list[str] = []
    for section in sections:
        register_id = section.get("register_id")
        if register_id in optional and not rows.get(register_id):
            continue
        schema = section.get("schema") or {}
        if section.get("is_list"):
            table = _table_widget(schema)
            if table and table.get("widget-required") is True and widget_state(table, values)[0]                     and not rows.get(register_id):
                title = say.text(section.get("title"), section.get("title") or section.get("section_id") or "")
                problems.append(say(list_key, section=title))
            continue
        problems += _section_problems(section, register_id, values, documents, say, keys)
    return list(dict.fromkeys(problems))


def _plain(record) -> dict:
    """A record as a dict: payloads already are, rows give their columns."""
    if isinstance(record, dict):
        return record
    from sqlalchemy import inspect

    return {attr.key: getattr(record, attr.key) for attr in inspect(record).mapper.column_attrs}


def fayda_id(value) -> str | None:
    if not isinstance(value, str):
        return None
    compact = "".join(value.split())
    return compact or None


def holder_name(row) -> str:
    name = _get(row, "record_name")
    if not _blank(name):
        return str(name)
    parts = [_get(row, f) for f in ("first_name", "middle_name", "last_name")]
    return " ".join(str(p) for p in parts if not _blank(p)) or "an unnamed farmer"


def _get(row, key: str):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


# On a farmer's form a household is picked or entered, never both and never
# required alongside the other: its sections are checked once the submission
# holds a household (household_intake.py checks that one of the two exists).
OPTIONAL_HOUSEHOLD_REGISTERS = ("Household", "HouseholdMember")


async def form_sections(form_id: str, session) -> list[dict]:
    """The form's sections, in order, with their register and kind."""
    from openg2p_registry_core.models import (
        G2PIntakeFormUITab,
        G2PIntakeFormUITabSection,
        G2PRegisterSection,
    )
    from sqlalchemy import select

    result = await session.execute(
        select(
            G2PRegisterSection.section_id,
            G2PRegisterSection.section_ui_schema,
            G2PRegisterSection.section_register_id,
            G2PRegisterSection.is_list,
        )
        .join(G2PIntakeFormUITabSection, G2PIntakeFormUITabSection.section_id == G2PRegisterSection.section_id)
        .join(G2PIntakeFormUITab, G2PIntakeFormUITab.tab_id == G2PIntakeFormUITabSection.tab_id)
        .where(G2PIntakeFormUITab.form_id == str(form_id))
        .order_by(G2PIntakeFormUITab.tab_order, G2PIntakeFormUITabSection.section_order)
    )
    sections = []
    for section_id, schema, register_id, is_list in result.all():
        schema = schema or {}
        sections.append({"section_id": section_id, "title": schema.get("section-title"), "schema": schema,
                         "register_id": register_id, "is_list": bool(is_list)})
    return sections


async def optional_register_ids(session) -> list[str]:
    from openg2p_registry_core.models import G2PRegisterDefinition
    from sqlalchemy import select

    result = await session.execute(
        select(G2PRegisterDefinition.register_id).where(
            G2PRegisterDefinition.register_mnemonic.in_(OPTIONAL_HOUSEHOLD_REGISTERS)))
    return list(result.scalars().all())


async def intake_rows(register_id: str, submission_id: str, session) -> list:
    """The submission's rows of one register (an empty list when the register
    has no intake table in this build)."""
    import importlib

    from openg2p_registry_core.models import G2PRegisterDefinition
    from sqlalchemy import select

    mnemonic = (await session.execute(
        select(G2PRegisterDefinition.register_mnemonic).where(G2PRegisterDefinition.register_id == register_id)
    )).scalar()
    if not mnemonic:
        return []
    model = getattr(importlib.import_module("openg2p_registry_extensions.register_domain.models"),
                    f"G2PIntakeForm{mnemonic}", None)
    if model is None:
        return []
    result = await session.execute(select(model).where(model.submission_id == str(submission_id)))
    return list(result.scalars().all())


async def saved_document_labels(submission_id: str, session) -> dict[str, set[str]]:
    from openg2p_registry_core.models import G2PIntakeFormSectionDocuments
    from sqlalchemy import select

    result = await session.execute(
        select(G2PIntakeFormSectionDocuments.section_id, G2PIntakeFormSectionDocuments.label).where(
            G2PIntakeFormSectionDocuments.submission_id == str(submission_id)
        )
    )
    documents: dict[str, set[str]] = {}
    for section_id, label in result.all():
        documents.setdefault(section_id, set()).add(label)
    return documents


async def check_form_complete(submission, session, messages: dict) -> list[str]:
    """The required fields of every section of the submission's form, over
    every register the form holds (membership, household, lands, crops, farm
    inputs, livestock and the documents as much as the farmer's own record)."""
    sections = await form_sections(submission.form_id, session)
    rows = {}
    for register_id in dict.fromkeys(s["register_id"] for s in sections):
        rows[register_id] = await intake_rows(register_id, submission.submission_id, session)
    documents = await saved_document_labels(submission.submission_id, session)
    return required_problems(sections, rows, documents, messages,
                             optional_registers=await _optional_for(submission, session))


async def _optional_for(submission, session) -> list[str]:
    """The household sections are optional only on a farmer's form; a
    household's own form requires them."""
    from openg2p_registry_core.models import G2PRegisterDefinition
    from sqlalchemy import select

    mnemonic = await session.scalar(
        select(G2PRegisterDefinition.register_mnemonic).where(
            G2PRegisterDefinition.register_id == submission.register_id))
    return [] if mnemonic in OPTIONAL_HOUSEHOLD_REGISTERS else await optional_register_ids(session)


async def fayda_id_holder(fin: str, *, internal_record_id: str | None, submission_id: str | None, session):
    """('registered' | 'pending', row) for the first other farmer holding `fin`."""
    from openg2p_registry_core.models import G2PIntakeFormSubmission
    from openg2p_registry_core.models.enum import (
        ApprovalStatusEnum,
        IntakeFormStatusEnum,
        RecordStatusEnum,
    )
    from openg2p_registry_extensions.register_domain.models import (
        G2PIntakeFormFarmer,
        G2PRegisterFarmer,
    )
    from sqlalchemy import func, select

    compact = func.replace(G2PRegisterFarmer.foundational_id, " ", "")
    query = select(G2PRegisterFarmer).where(
        compact == fin, G2PRegisterFarmer.record_status != RecordStatusEnum.ARCHIVED.value
    )
    if internal_record_id:
        query = query.where(G2PRegisterFarmer.internal_record_id != str(internal_record_id))
    row = (await session.execute(query.limit(1))).scalars().first()
    if row is not None:
        return "registered", row

    compact = func.replace(G2PIntakeFormFarmer.foundational_id, " ", "")
    query = (
        select(G2PIntakeFormFarmer, G2PIntakeFormSubmission.application_reference)
        .join(G2PIntakeFormSubmission, G2PIntakeFormSubmission.submission_id == G2PIntakeFormFarmer.submission_id)
        .where(
            compact == fin,
            G2PIntakeFormSubmission.draft_status == IntakeFormStatusEnum.FINAL.value,
            G2PIntakeFormSubmission.approval_status == ApprovalStatusEnum.PENDING.value,
        )
    )
    if submission_id:
        query = query.where(G2PIntakeFormFarmer.submission_id != str(submission_id))
    if internal_record_id:
        query = query.where(G2PIntakeFormFarmer.internal_record_id != str(internal_record_id))
    found = (await session.execute(query.limit(1))).first()
    if found is not None:
        return "pending", found
    return None


async def check_fayda_id_unique(record, label: str, session, messages: dict, *, submission_id=None) -> str | None:
    """A sentence when another farmer already holds this record's Fayda ID."""
    fin = fayda_id(_get(record, "foundational_id"))
    if not fin:
        return None
    held = await fayda_id_holder(
        fin, internal_record_id=_get(record, "internal_record_id"), submission_id=submission_id, session=session
    )
    if held is None:
        return None
    say = _Messages(messages or {})
    kind, found = held
    if kind == "registered":
        record_id = _get(found, "functional_record_id") or _get(found, "internal_record_id")
        return say("fayda_fin_registered", label=label, fin=fin, name=holder_name(found), record=record_id)
    row, reference = found
    return say("fayda_fin_pending", label=label, fin=fin, name=holder_name(row),
               record=reference or _get(row, "submission_id"))
