#!/usr/bin/env python3
"""Inline the farmer's reference lists into the register metadata as static options.

The staff portal resolves a select whose data source is
``{"type": "api", "service": "attributes", "params": {"attribute_id": X}}``
against MASTER DATA (``/api/attributes/values`` proxies to
MASTERDATA_BACKEND_API_URL), never against this registry's own
``g2p_attribute_values``. The farmer lists only ever reach the registry
database (``meta_data/lookup-data``), the Ethiopia country pack Master Data is
seeded from carries none of the livestock/language lists and only a 12-value
crop list, and Master Data's value query hides pack lists that sit under a
domain anyway. Result: every such dropdown was empty in every environment.

Until Master Data carries these lists, the widgets carry them inline, the same
way the language selects do. This script is the single way to (re)generate
them: it reads the fixture SQL and rewrites each attribute-backed data source
in place, so the options can never be hand-edited out of step with the
fixture. The generated source keeps ``attribute_id`` next to ``options`` so a
later run (or ``tests/test_static_options_match_fixture.py``) can tell which
fixture list it came from; the widget ignores the extra key.

Option value is the fixture's value_code, which is what existing records and
the sample data store (WHEAT, GOAT, INHERITANCE), not the value_id.

Run from the repo root:  python3 scripts/sync-static-options.py [--check]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "farmer-extension" / "src" / "openg2p_registry_farmer_extension" / "meta_data"
LOOKUP = EXT / "lookup-data"
META = EXT / "register-metadata"

# ('value_id','attribute_id','value_code','value_display',parent,sort_order)
ROW = re.compile(
    r"^\('(?P<id>[^']*)','(?P<attr>[^']*)','(?P<code>(?:[^']|'')*)','(?P<display>(?:[^']|'')*)',"
    r"(?:NULL|'[^']*'),(?P<sort>\d+)\)",
    re.M,
)


def fixture_lists() -> dict[str, list[tuple[str, str]]]:
    lists: dict[str, list[tuple[int, str, str]]] = {}
    for name in ("g2p_attribute_values.sql", "g2p_attribute_values_defaults.sql"):
        text = (LOOKUP / name).read_text(encoding="utf-8")
        for m in ROW.finditer(text):
            lists.setdefault(m["attr"], []).append(
                (int(m["sort"]), m["code"].replace("''", "'"), m["display"].replace("''", "'"))
            )
    return {
        attr: [(code, display) for _, code, display in sorted(rows)]
        for attr, rows in lists.items()
    }


def static_source(attr: str, options: list[tuple[str, str]], indent: str | None) -> str:
    items = [{"label": display, "value": code} for code, display in options]
    compact = dict(ensure_ascii=False, separators=(", ", ": "))
    if indent is None:
        return json.dumps({"type": "static", "attribute_id": attr, "options": items}, **compact)
    inner = indent + "  "
    lines = ",\n".join(inner + "  " + json.dumps(item, **compact) for item in items)
    return (
        "{\n"
        f'{inner}"type": "static",\n'
        f'{inner}"attribute_id": "{attr}",\n'
        f'{inner}"options": [\n{lines}\n{inner}]\n'
        f"{indent}}}"
    )


def object_end(text: str, start: int) -> int:
    """Index just past the JSON object whose '{' is at start."""
    depth, i, in_str = 0, start, False
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced object")


SOURCE_KEY = re.compile(r'"widget-data-source"\s*:\s*\{')


def source_attribute(source: dict) -> str | None:
    """The fixture list a data source draws from, for either form it takes."""
    if source.get("type") == "api" and source.get("service") == "attributes":
        return (source.get("params") or {}).get("attribute_id")
    if source.get("type") == "static" and source.get("attribute_id"):
        return source["attribute_id"]
    return None


def rewrite(text: str, lists: dict[str, list[tuple[str, str]]]) -> tuple[str, list[str]]:
    out, pos, done = [], 0, []
    for m in SOURCE_KEY.finditer(text):
        if m.start() < pos:
            continue
        obj_start = m.end() - 1
        obj_end = object_end(text, obj_start)
        raw = text[obj_start:obj_end]
        try:
            source = json.loads(raw.replace("''", "'"))
        except json.JSONDecodeError:
            continue
        attr = source_attribute(source)
        if attr is None:
            continue
        if attr not in lists:
            print(f"  ! {attr}: no list in the fixture, left as is", file=sys.stderr)
            continue
        # Pretty-printed (zz_) files: keep the object on multiple lines at the
        # key's indentation. Single-line INSERT rows stay single-line.
        line_start = text.rfind("\n", 0, m.start()) + 1
        prefix = text[line_start:m.start()]
        indent = prefix if prefix.strip() == "" else None
        rendered = static_source(attr, lists[attr], indent)
        if indent is None:
            # Inside a single-quoted SQL literal an apostrophe is doubled.
            rendered = rendered.replace("'", "''")
        out.append(text[pos:obj_start])
        out.append(rendered)
        pos = obj_end
        done.append(attr)
    out.append(text[pos:])
    return "".join(out), done


def main() -> int:
    check = "--check" in sys.argv[1:]
    lists = fixture_lists()
    drift = False
    for path in sorted(META.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        new, done = rewrite(text, lists)
        if new != text:
            drift = True
            if check:
                print(f"{path.name}: static options out of date ({', '.join(sorted(set(done)))})")
            else:
                path.write_text(new, encoding="utf-8", newline="\n")
                print(f"{path.name}: rewrote {len(done)} data source(s): {', '.join(sorted(set(done)))}")
    if check and drift:
        return 1
    if not drift:
        print("static options already match the fixture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
