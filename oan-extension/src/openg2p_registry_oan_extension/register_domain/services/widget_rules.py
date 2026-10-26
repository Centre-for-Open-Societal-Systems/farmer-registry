"""The value rules a section's widgets declare, applied on the server.

The staff UI enforces `widget-data-validation` (pattern, minLength, maxLength,
min, max) in the browser; core does not. The OpenG2P docs place server-side
domain rules in `validate_domain_attributes`, so the domain services apply the
same rules from the same section metadata, and a rule is still written once.

Besides those rules, a widget's type says what kind of value it takes: a
boolean widget yes or no, a number widget a number (a whole one when its
format says "integer"), a date widget a date, a select with a static list one
of its options. A value of the wrong kind is reported here, by field, instead
of reaching the database and coming back as an unexplained SYS-ERR-001.

Every message names the field by its label, as the form shows it, and says
what to enter instead: "<label>: <what is wrong>. <what to do>." A message is
a translation key with an English default, so a language can reword it.

Rules about a value's form are applied only to values that are present.
Whether a field is required depends on the section and on conditions the UI
evaluates, so for a section's own fields that stays with the UI and with the
domain rules in code. A table row is different: it is a whole record of its
register, so a column marked required, with no condition on it, is required
in every new row and in any row that sends it blank.

This module has no database or framework imports, so it can be tested alone.
"""

import logging
import re
from collections.abc import Iterable

_logger = logging.getLogger("oan-widget-rules")

RULE_KEYS = ("pattern", "minLength", "maxLength", "min", "max")

# register id -> field -> rules
Rules = dict[str, dict[str, dict]]

# Message keys and their English text. {label} is the field's label, the other
# names are the rule's values.
MESSAGES = {
    "oan_rule_pattern": "{label}: {message}.",
    "oan_rule_pattern_default": "{label}: the format is not valid. Check the value and enter it again.",
    "oan_rule_min_length": "{label}: too short. Enter at least {minLength} characters.",
    "oan_rule_max_length": "{label}: too long. Enter at most {maxLength} characters.",
    "oan_rule_min": "{label}: {value} is too small. Enter {min} or more.",
    "oan_rule_max": "{label}: {value} is too large. Enter {max} or less.",
    "oan_rule_boolean": "{label}: answer Yes or No.",
    "oan_rule_integer": "{label}: \"{value}\" is not a whole number. Enter digits only, for example 12.",
    "oan_rule_number": "{label}: \"{value}\" is not a number. Enter a number, for example 2.5.",
    "oan_rule_date": "{label}: \"{value}\" is not a date. Pick the date from the calendar (DD/MM/YYYY).",
    "oan_rule_option": "{label}: \"{value}\" is not one of the choices. Pick one from the list.",
    "oan_rule_required": "{label}: this is required. Fill it in on every row before saving.",
    "oan_rule_year_range": "{label}: enter a whole year from 1900 to {year}, or leave it empty.",
    "oan_rule_future_date": "{label}: the date is in the future. Choose today or an earlier date.",
}

_TYPES = {
    "boolean": "boolean",
    "date": "date",
    "oan-ethiopian-date-input": "date",
    "number": "number",
}


def _widgets(node):
    """Every widget in a section schema, at any depth of panels."""
    if isinstance(node, dict):
        if "widget" in node and ("widget-data-path" in node or "column-key" in node):
            yield node
        for value in node.values():
            yield from _widgets(value)
    elif isinstance(node, list):
        for item in node:
            yield from _widgets(item)


def collect_rules(sections: Iterable[tuple[str, dict]]) -> Rules:
    """Rules per register and field, from (section_register_id, ui_schema) pairs.

    A widget's path is "<register id>.<field>". A table widget's path is
    "<register id>.records", and its columns are fields of that register.
    """
    rules: Rules = {}
    for section_register_id, schema in sections:
        for widget in _widgets(schema or {}):
            path = widget.get("widget-data-path")
            if isinstance(path, str) and "." in path:
                register_id, field = path.split(".", 1)
            elif widget.get("column-key"):
                register_id, field = section_register_id, widget["column-key"]
            else:
                continue
            if field == "records":
                for column in widget.get("widget-data-columns") or []:
                    _add(rules, register_id, column.get("column-key"), column, column=True)
            else:
                _add(rules, register_id, field, widget)
    return rules


def _kind(widget: dict) -> str | None:
    kind = _TYPES.get(widget.get("widget"))
    if kind == "number" and (widget.get("widget-data-format") or {}).get("numericType") == "integer":
        return "integer"
    return kind


def _options(widget: dict) -> list | None:
    source = widget.get("widget-data-source") or {}
    if widget.get("widget") not in {"select", "multi-select"} or source.get("type") != "static":
        return None
    values = [o.get("value") for o in source.get("options") or [] if isinstance(o, dict)]
    return values or None


def _conditional(widget: dict) -> bool:
    actions = (widget.get("widget-data-options") or {}).get("actions") or []
    return any(isinstance(a, dict) and a.get("action") in ("show", "hide", "require") for a in actions)


def _add(rules: Rules, register_id: str, field: str | None, widget: dict, column: bool = False) -> None:
    if not field or "." in field:
        return
    validation = widget.get("widget-data-validation") or {}
    found = {k: validation[k] for k in RULE_KEYS if validation.get(k) is not None}
    for key in ("patternMessage", "minMessage", "maxMessage"):
        if validation.get(key):
            found[key] = validation[key]
    kind = _kind(widget)
    if kind:
        found["type"] = kind
    if widget.get("widget") == "multi-select":
        found["multiple"] = True
    options = _options(widget)
    if options:
        found["options"] = options
    if column and widget.get("widget-required") is True and widget.get("widget") != "parent-lookup"             and not _conditional(widget):
        found["required"] = True
    if not found:
        return
    if widget.get("widget-label"):
        found["label"] = widget["widget-label"]
    existing = rules.setdefault(register_id, {}).setdefault(field, {})
    for key, value in found.items():
        if key == "type" and {existing.get(key), value} == {"number", "integer"}:
            # One screen takes any number and another a whole one: whole.
            existing[key] = "integer"
            continue
        if key in existing and existing[key] != value:
            # Two sections disagree. Keep the first and say so, rather than
            # rejecting what one of the two screens allows.
            if key != "label":
                _logger.warning("Conflicting %s for %s.%s: %r and %r", key, register_id, field, existing[key], value)
            continue
        existing[key] = value


_compiled: dict[str, re.Pattern | None] = {}


def _regex(pattern: str) -> re.Pattern | None:
    if pattern not in _compiled:
        try:
            _compiled[pattern] = re.compile(pattern)
        except re.error as error:
            # Written for the browser's regex engine and not valid in Python's.
            _logger.warning("Skipping pattern %r: %s", pattern, error)
            _compiled[pattern] = None
    return _compiled[pattern]


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _is_date(value) -> bool:
    if hasattr(value, "year") and hasattr(value, "month"):
        return True
    match = _DATE.match(value) if isinstance(value, str) else None
    if not match:
        return False
    year, month, day = (int(g) for g in match.groups())
    if not 1 <= month <= 12 or day < 1:
        return False
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    days = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]
    return day <= days


def _same_option(value, option) -> bool:
    if isinstance(value, bool) or isinstance(option, bool):
        return str(value).lower() == str(option).lower()
    return value == option or str(value) == str(option)


def _type_problem(kind: str, value) -> str | None:
    if kind == "boolean":
        return None if isinstance(value, bool) else "oan_rule_boolean"
    if kind == "date":
        return None if _is_date(value) else "oan_rule_date"
    number = _number(value)
    if number is None:
        return "oan_rule_integer" if kind == "integer" else "oan_rule_number"
    if kind == "integer" and not number.is_integer():
        return "oan_rule_integer"
    return None


class _Say:
    """Formats a message key with the translations, falling back to English."""

    def __init__(self, messages: dict[str, str]):
        self.messages = messages

    def text(self, key: str | None, default: str | None = None) -> str:
        if not key:
            return default or ""
        found = self.messages.get(key)
        return found if isinstance(found, str) and found else (default if default is not None else key)

    def label(self, key: str | None, field: str) -> str:
        """The field as the form names it: its label's translation, else the
        field's, else the label key itself."""
        for candidate in (key, field):
            found = self.messages.get(candidate) if candidate else None
            if isinstance(found, str) and found:
                return found
        return key or field

    def __call__(self, key: str, **params) -> str:
        template = self.text(key, MESSAGES.get(key, key))
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            return MESSAGES.get(key, key).format(**params)


def check_record(record: dict, field_rules: dict[str, dict], messages: dict[str, str] | None = None) -> list[str]:
    """Problems with one record, each a sentence naming the field and the fix."""
    say = _Say(messages or {})
    problems = []
    new = not record.get("internal_record_id")
    for field, rule in field_rules.items():
        value = record.get(field)
        label = say.label(rule.get("label"), field)
        if value is None or (isinstance(value, str) and not value.strip()) or (rule.get("multiple") and value == []):
            if rule.get("required") and (new or field in record):
                problems.append(say("oan_rule_required", label=label))
            continue
        if "type" in rule:
            problem = _type_problem(rule["type"], value)
            if problem:
                problems.append(say(problem, label=label, value=value))
                continue
        if "options" in rule:
            selected = value if rule.get("multiple") and isinstance(value, list) else [value]
            invalid = [item for item in selected if not any(_same_option(item, option) for option in rule["options"])]
            if invalid:
                problems.append(say("oan_rule_option", label=label, value=", ".join(map(str, invalid))))
                continue
        if isinstance(value, str):
            text = value
            if "pattern" in rule:
                regex = _regex(rule["pattern"])
                if regex and not regex.fullmatch(text):
                    key = rule.get("patternMessage")
                    if key:
                        problems.append(say("oan_rule_pattern", label=label, message=say.text(key).rstrip(".")))
                    else:
                        problems.append(say("oan_rule_pattern_default", label=label))
            if "minLength" in rule and len(text) < int(rule["minLength"]):
                problems.append(say("oan_rule_min_length", label=label, minLength=rule["minLength"]))
            if "maxLength" in rule and len(text) > int(rule["maxLength"]):
                problems.append(say("oan_rule_max_length", label=label, maxLength=rule["maxLength"]))
        number = _number(value)
        if number is not None and rule.get("type") not in ("boolean", "date"):
            for bound, key, out in (("min", "oan_rule_min", number < float(rule.get("min", 0))),
                                    ("max", "oan_rule_max", number > float(rule.get("max", 0)))):
                if bound in rule and out:
                    custom = rule.get(bound + "Message")
                    if custom and custom in say.messages:
                        problems.append(f"{label}: {say.text(custom).rstrip('.')}.")
                    else:
                        problems.append(say(key, label=label, value=value, **{bound: rule[bound]}))
    return problems


def normalize_record(record: dict, field_rules: dict[str, dict]) -> None:
    """Numbers sent as text become numbers, so the database driver takes them.

    Only a value that is a valid number of the widget's kind is converted; any
    other value is left for check_record to report.
    """
    for field, rule in field_rules.items():
        value = record.get(field)
        if rule.get("type") not in ("integer", "number") or not isinstance(value, str) or not value.strip():
            continue
        number = _number(value.strip())
        if number is None:
            continue
        if rule["type"] == "integer":
            if number.is_integer():
                record[field] = int(number)
        else:
            record[field] = number
