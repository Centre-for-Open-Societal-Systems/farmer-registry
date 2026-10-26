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
  required.
- Duplicate matching uses names and birth date, never the Fayda ID, so the
  same FIN or FAN could be registered for a second farmer. An ID already held
  by a register record, or by another submitted form waiting for approval, is
  refused on section save and at submit, naming who holds it.

Approval stays the control: nothing here asks for a Fayda verification.

The functions above `check_form_complete` have no database or framework
imports, so they can be tested alone.
"""

from collections.abc import Iterable

from .widget_rules import _Say

MESSAGES = {
    "oan_form_missing": "{section}: {label} is required. Open {section}, fill it in and save, then submit again.",
    "oan_form_document_missing": (
        "{section}: {label} is required. Open {section}, add the file and save, then submit again."
    ),
    "oan_fin_registered": (
        "{label}: {fin} is already registered to {name} ({record}). Open that record instead of "
        "registering the farmer again; if the ID was mistyped, correct it."
    ),
    "oan_fin_pending": (
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
        title = say.text(section.get("title"), section.get("title") or section.get("section_id") or "")
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
                    problems.append(say("oan_form_document_missing", section=title, label=label))
            elif _blank(value_at(values, path)):
                problems.append(say("oan_form_missing", section=title, label=label))
    return list(dict.fromkeys(problems))


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


def _record_values(row) -> dict:
    from sqlalchemy import inspect

    return {attr.key: getattr(row, attr.key) for attr in inspect(row).mapper.column_attrs}


async def _form_sections(form_id: str, session) -> list[dict]:
    from openg2p_registry_core.models import (
        G2PIntakeFormUITab,
        G2PIntakeFormUITabSection,
        G2PRegisterSection,
    )
    from sqlalchemy import select

    result = await session.execute(
        select(G2PRegisterSection.section_id, G2PRegisterSection.section_ui_schema)
        .join(G2PIntakeFormUITabSection, G2PIntakeFormUITabSection.section_id == G2PRegisterSection.section_id)
        .join(G2PIntakeFormUITab, G2PIntakeFormUITab.tab_id == G2PIntakeFormUITabSection.tab_id)
        .where(G2PIntakeFormUITab.form_id == str(form_id), G2PRegisterSection.is_list.is_(False))
        .order_by(G2PIntakeFormUITab.tab_order, G2PIntakeFormUITabSection.section_order)
    )
    sections = []
    for section_id, schema in result.all():
        schema = schema or {}
        sections.append({"section_id": section_id, "title": schema.get("section-title"), "schema": schema})
    return sections


async def check_form_complete(submission, register_id: str, farmer, session, messages: dict) -> list[str]:
    """The required fields of every section of the submission's form."""
    from openg2p_registry_core.models import G2PIntakeFormSectionDocuments
    from sqlalchemy import select

    sections = await _form_sections(submission.form_id, session)
    result = await session.execute(
        select(G2PIntakeFormSectionDocuments.section_id, G2PIntakeFormSectionDocuments.label).where(
            G2PIntakeFormSectionDocuments.submission_id == str(submission.submission_id)
        )
    )
    documents: dict[str, set[str]] = {}
    for section_id, label in result.all():
        documents.setdefault(section_id, set()).add(label)
    values = {register_id: _record_values(farmer) if farmer is not None else {}}
    return missing_required(sections, register_id, values, documents, messages)


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
        return say("oan_fin_registered", label=label, fin=fin, name=holder_name(found), record=record_id)
    row, reference = found
    return say("oan_fin_pending", label=label, fin=fin, name=holder_name(row),
               record=reference or _get(row, "submission_id"))
