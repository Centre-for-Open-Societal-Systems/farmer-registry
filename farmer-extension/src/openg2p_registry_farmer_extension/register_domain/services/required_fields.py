"""Required fields of the Farmer forms, read from the section metadata.

`widget-required` in a section's UI schema is the one place the rule lives:
the staff UI marks the field, and the save and submit checks
(required_intake.py) read the same flag, on every channel (web, ODK, partner).
Making a field optional is a metadata change, not a code change.

The rules follow the staff UI (form_integrity.widget_state):

- a field hidden by a show/hide condition is not required;
- a `require` condition makes a field required while it matches;
- a list (table) section needs at least one row only when the table widget
  itself is `widget-required`; each row must carry its required columns.

This module has no database or framework imports, so it can be tested alone.
"""

from .form_integrity import _blank, _widgets, widget_state
from .widget_rules import _Say

# Widgets whose value is not a field of the section's record, or that other
# checks own: a table is its own register, a lookup picks a parent record (the
# household check), display and group widgets hold no input.
SKIPPED = {"table", "dialog-table", "register-lookup", "parent-lookup", "display", "header-section"}
TABLES = ("table", "dialog-table")

MESSAGES = {
    "required_fill_in": "{section}: fill in {fields}",
    "required_fill_in_row": "{section}, row {row}: fill in {fields}",
    "required_add_file": "{section}: add {fields}",
    "required_add_row": "{section}: add at least one row",
}


def humanize(key: str | None) -> str:
    """A readable name for a key nobody translated: no underscores or hyphens."""
    text = " ".join(str(key or "").replace("_", " ").replace("-", " ").split())
    return text[:1].upper() + text[1:]


class _Words:
    """Section titles and field labels as the form shows them."""

    def __init__(self, messages: dict | None):
        self.say = _Say(messages or {})

    def title(self, schema: dict, fallback: str = "") -> str:
        key = (schema or {}).get("section-title")
        translated = self.say.messages.get(key) if key else None
        return translated if isinstance(translated, str) and translated else humanize(key or fallback)

    def label(self, widget: dict, field: str) -> str:
        for candidate in (widget.get("widget-label"), field):
            found = self.say.messages.get(candidate) if candidate else None
            if isinstance(found, str) and found:
                return found
        return humanize(widget.get("widget-label") or field)

    def text(self, key: str, **params) -> str:
        template = self.say.text(key, MESSAGES[key])
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            return MESSAGES[key].format(**params)


def value_path(widget: dict) -> str | None:
    path = widget.get("widget-data-path")
    if isinstance(path, dict):
        path = path.get("value")
    return path if isinstance(path, str) else None


def field_of(widget: dict) -> str | None:
    """The record field a widget writes: the last part of its data path, or
    the column key of a table column."""
    if widget.get("column-key"):
        return str(widget["column-key"])
    path = value_path(widget)
    return path.split(".")[-1] if path else None


def table_of(schema: dict) -> dict | None:
    """The table widget of a list section."""
    stack = [schema]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("widget") in TABLES and "widget-data-columns" in node:
                return node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None


def _file_labels(widget: dict, field: str) -> set:
    return {widget.get("widget-label"), field, widget.get("widget-id")}


def missing_in_record(
    widgets, record: dict, values: dict, words: _Words, saved_files: set | None = None
) -> tuple[list[str], list[str]]:
    """(fields to fill in, files to add) for one record.

    `values` is what conditions are evaluated against: register id -> record
    for a single-record section, the row itself for a table row.
    """
    fill: list[str] = []
    files: list[str] = []
    for widget in widgets:
        if widget.get("widget") in SKIPPED or widget.get("widget-readonly"):
            continue
        field = field_of(widget)
        if not field:
            continue
        visible, required = widget_state(widget, values)
        if not (visible and required):
            continue
        label = words.label(widget, field)
        if widget.get("widget") == "file":
            # A document category names itself by its title (DocumentsWidget).
            title = (widget.get("widget-data-options") or {}).get("title")
            if title:
                label = words.label({"widget-label": title}, field)
            if not (_file_labels(widget, field) & (saved_files or set())) and label not in files:
                files.append(label)
        elif _blank(record.get(field)) and label not in fill:
            fill.append(label)
    return fill, files


def section_problems(
    schema: dict,
    is_list: bool,
    records: list[dict],
    values: dict,
    messages: dict | None = None,
    saved_files: set | None = None,
) -> list[str]:
    """One sentence per thing a section still needs, in the section's words.

    `records` are the section's records as they will be stored (the surviving
    rows); `values` maps register ids to records, for conditions that look at
    another section of the same form.
    """
    words = _Words(messages)
    title = words.title(schema)
    problems: list[str] = []
    if is_list:
        table = table_of(schema)
        if table is None:
            return problems
        if table.get("widget-required") is True and not records:
            return [words.text("required_add_row", section=title)]
        columns = [c for c in table.get("widget-data-columns") or [] if isinstance(c, dict)]
        for number, row in enumerate(records, start=1):
            fill, _ = missing_in_record(columns, row, {**row, **values}, words)
            if fill:
                problems.append(words.text("required_fill_in_row", section=title, row=number, fields=", ".join(fill)))
        return problems
    record = records[0] if records else {}
    fill, files = missing_in_record(_widgets(schema), record, values, words, saved_files)
    if fill:
        problems.append(words.text("required_fill_in", section=title, fields=", ".join(fill)))
    if files:
        problems.append(words.text("required_add_file", section=title, fields=", ".join(files)))
    return problems
