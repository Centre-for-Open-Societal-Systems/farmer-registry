"""G2R-593: the Household duplicate check must not flag unrelated households.

Core scores a candidate pair as the weighted average of per-field scores
(exact = 0 or 100, fuzzy = pg_trgm similarity * 100) and flags it when the
score reaches the register's dedup_threshold_score. A count field such as
size_of_group has few distinct values, so it must never be able to reach the
threshold on its own. address_line_1 is the household's identity field.

    uv run --no-project --with pytest pytest farmer-extension/tests/test_household_dedup_weights.py
"""

import json
import re
from pathlib import Path

_META = Path(__file__).parents[1] / "src/openg2p_registry_farmer_extension/meta_data/register-metadata"
HOUSEHOLD = "9055ab43-c85d-4833-bd00-ca657bb72644"


def _household_schema():
    for line in (_META / "g2p_register_schemas.sql").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"('{HOUSEHOLD}'"):
            return json.loads(re.match(r"\('[^']+','(.*?\])','\[", line).group(1))
    raise AssertionError("Household row not found")


def _threshold():
    for line in (_META / "g2p_register_definitions.sql").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"('{HOUSEHOLD}'"):
            # ...,'has_image','dedup_is_enabled','dedup_threshold_score',...
            return float(re.search(r"'FALSE','TRUE',(\d+),", line).group(1))
    raise AssertionError("Household definition not found")


def _trigrams(text):
    grams = set()
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        padded = f"  {word} "
        grams |= {padded[i:i + 3] for i in range(len(padded) - 2)}
    return grams


def _similarity(a, b):  # pg_trgm similarity()
    ta, tb = _trigrams(a), _trigrams(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def _score(schema, a, b):
    total = sum(f["weight"] for f in schema)
    got = 0.0
    for f in schema:
        x, y = a[f["field_name"]], b[f["field_name"]]
        s = (100.0 if x == y else 0.0) if f["match_type"] == "exact" else _similarity(str(x), str(y)) * 100
        got += f["weight"] * s
    return got / total


def _flagged(a, b):
    return _score(_household_schema(), a, b) >= _threshold()


def test_threshold_is_the_register_value():
    assert _threshold() == 70


def test_unrelated_households_of_same_size_are_not_duplicates():
    a = {"size_of_group": 5, "address_line_1": "Kebele 03 House 12 Bole"}
    b = {"size_of_group": 5, "address_line_1": "Woreda 7 Gondar Zuria"}
    assert not _flagged(a, b)


def test_size_alone_cannot_reach_the_threshold():
    a = {"size_of_group": 5, "address_line_1": "aaaa"}
    b = {"size_of_group": 5, "address_line_1": "zzzz"}
    assert _score(_household_schema(), a, b) < _threshold()


def test_same_address_and_same_size_is_a_duplicate():
    a = {"size_of_group": 5, "address_line_1": "Kebele 03 House 12 Bole"}
    b = {"size_of_group": 5, "address_line_1": "Kebele 03 House 12 Bole"}
    assert _flagged(a, b)


def test_address_is_the_dominant_weight():
    weights = {f["field_name"]: f["weight"] for f in _household_schema()}
    assert weights["address_line_1"] > weights["size_of_group"]
