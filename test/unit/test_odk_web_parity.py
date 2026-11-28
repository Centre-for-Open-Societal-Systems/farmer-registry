"""The web intake and the ODK form ask for the same answers.

For each question that both of them ask, the web seed (site-configuration SQL) and the
XLSForm must agree on when an answer is mandatory: always, only for one answer
of another question, or never. A change on one side alone fails here.
"""

import json
import re
from pathlib import Path

import openpyxl
import pytest

REPO = Path(__file__).resolve().parents[2]
SEED = REPO / "farmer-extension/src/openg2p_registry_farmer_extension/meta_data/site-configuration"
FORM = REPO / "odk/ATI_Farmers_Profile_ODK_Form_v4.xlsx"
FARMER = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"

# web widget id -> (ODK question, when it is mandatory)
# "always", or (question it depends on, the answer that makes it mandatory)
PAIRS = {
    "has_national_id": ("national_id", "always"),
    "foundational_id": ("national_uid", ("has_national_id", True)),
    "rid": ("national_rid", ("has_national_id", False)),
    "farming_type": ("farming_type", "always"),
    "language_spoken": ("language", "always"),
    "source_of_income": ("income_source", "always"),
    "is_household_head": ("household_head", "always"),
}
# web question -> ODK question, and the web value -> the ODK choice name
ANSWERS = {"has_national_id": ("national_id", {True: "yes", False: "no"})}


def string_literals(sql):
    """The SQL string literals of a file, skipping -- comments (which may hold apostrophes)."""
    i, n = 0, len(sql)
    while i < n:
        if sql.startswith("--", i):
            i = sql.find("\n", i)
            i = n if i < 0 else i
        elif sql[i] == "'":
            j, parts = i + 1, []
            while j < n:
                if sql[j] == "'" and sql[j + 1 : j + 2] == "'":
                    parts.append("'")
                    j += 2
                elif sql[j] == "'":
                    break
                else:
                    parts.append(sql[j])
                    j += 1
            yield "".join(parts)
            i = j + 1
        else:
            i += 1


def seed_widgets():
    """Every widget object written in the seed, by widget id (later files win, as on a run)."""
    found = {}
    for path in sorted(SEED.glob("*.sql")):
        for raw in string_literals(path.read_text(encoding="utf-8")):
            text = raw.strip()
            if '"widget-id"' not in text or text[:1] not in "[{":
                continue
            try:
                value = json.loads(text)
            except ValueError:
                continue
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, dict) and "widget-id" in item:
                    found.setdefault(item["widget-id"], {}).update(item)
    return found


def web_rule(widget):
    """When the web makes this widget mandatory: "always", (field, value) or None."""
    if widget.get("widget-required"):
        return "always"
    options = widget.get("widget-data-options") or {}
    actions = options.get("actions") or ([options] if options.get("action") else [])
    for action in actions:
        if action.get("action") == "require":
            condition = action["condition"]
            assert condition.get("operator") == "equals", condition
            return condition["field"].split(".")[-1], condition["value"]
    return None


def odk_rows():
    sheet = openpyxl.load_workbook(FORM, read_only=True)["survey"]
    rows = list(sheet.iter_rows(values_only=True))
    head = [str(c).strip() if c else "" for c in rows[0]]
    return {
        str(r[head.index("name")]).strip(): dict(zip(head, r))
        for r in rows[1:]
        if r[head.index("name")]
    }


def odk_rule(row):
    """When ODK makes this question mandatory: "always", (question, choice) or None."""
    if str(row.get("required") or "").strip().lower() not in ("yes", "true", "true()"):
        return None
    relevant = str(row.get("relevant") or "").strip()
    if not relevant:
        return "always"
    match = re.fullmatch(r"\$\{(\w+)\}\s*=\s*'([^']*)'", relevant)
    assert match, f"relevant too complex to compare: {relevant}"
    return match.group(1), match.group(2)


@pytest.fixture(scope="module")
def web():
    return seed_widgets()


@pytest.fixture(scope="module")
def odk():
    return odk_rows()


@pytest.mark.parametrize("widget_id", sorted(PAIRS))
def test_web_and_odk_agree_on_when_an_answer_is_mandatory(widget_id, web, odk):
    question, expected = PAIRS[widget_id]
    assert widget_id in web, f"{widget_id} is not in the web seed"
    assert question in odk, f"{question} is not in the ODK form"
    web_says, odk_says = web_rule(web[widget_id]), odk_rule(odk[question])
    if expected == "always":
        assert web_says == "always", f"web {widget_id}: {web_says}"
        assert odk_says == "always", f"ODK {question}: {odk_says}"
        return
    field, value = expected
    assert web_says == (field, value), f"web {widget_id}: {web_says}"
    odk_field, choices = ANSWERS[field]
    assert odk_says == (odk_field, choices[value]), f"ODK {question}: {odk_says}"


def test_the_rid_stays_visible_for_either_answer(web):
    """A farmer with a Fayda ID may also hold an RID: it is shown for Yes and No,
    so a recorded RID is never hidden (and cleared on save)."""
    actions = web["rid"]["widget-data-options"]["actions"]
    shows = [a["condition"] for a in actions if a["action"] == "show"]
    assert shows == [{"field": f"{FARMER}.has_national_id", "operator": "notEmpty"}]
