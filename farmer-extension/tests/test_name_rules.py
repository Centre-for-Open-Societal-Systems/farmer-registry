"""The name rule: the pattern the staff UI runs, and the server check.

The pattern is read from the metadata seed, so these tests run the exact string
the widgets carry: in Python's re, and in a browser-style JavaScript RegExp when
node is installed. name_rules.py has no framework imports, so it is loaded by
path:

    uv run --no-project --with pytest python -I -m pytest farmer-extension/tests/test_name_rules.py
"""

import importlib.util
import json
import re
import shutil
import subprocess
import unicodedata
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[1] / "src/openg2p_registry_farmer_extension"
_spec = importlib.util.spec_from_file_location("name_rules", _ROOT / "register_domain/name_rules.py")
name_rules = importlib.util.module_from_spec(_spec)
sys.modules["name_rules"] = name_rules
_spec.loader.exec_module(name_rules)

_SEED = (_ROOT / "meta_data/zz-oan/19_name_rules.sql").read_text(encoding="utf-8")
PATTERN = re.search(r"\$pattern\$(.*?)\$pattern\$", _SEED, re.S).group(1)

ACCEPT = ["Abebe", "አበበ", "O'Neil", "O\u2019Neil", "Mary-Jane", "Abebe Kebede", "José", "Nu\u0301ñez", "a" * 100]
REJECT = ["E2E Test", "Abebe1", "", "  ", "a" * 101, "Abebe_Kebede", "Abebe.", "'-", "Abebe\nKebede", "١٢٣"]

NODE = shutil.which("node")


def python_accepts(text: str) -> bool:
    return re.search(PATTERN, text) is not None


def node_results(texts: list[str], flags: str) -> list[bool]:
    # The pattern and the texts go in on stdin; they are too long for a command line.
    script = (
        "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "const r = new RegExp(input.pattern, input.flags);"
        "console.log(JSON.stringify(input.texts.map(s => r.test(s))));"
    )
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True, encoding="utf-8",
                          input=json.dumps({"pattern": PATTERN, "flags": flags, "texts": texts}))
    return json.loads(done.stdout)


def test_the_pattern_has_no_property_escapes():
    assert r"\p{" not in PATTERN
    assert PATTERN.startswith("^") and PATTERN.endswith("$")


@pytest.mark.parametrize("text", ACCEPT)
def test_python_accepts(text):
    assert python_accepts(text)


@pytest.mark.parametrize("text", REJECT)
def test_python_rejects(text):
    assert not python_accepts(text)


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("flags", ["", "u"])
def test_javascript_gives_the_same_results(flags):
    texts = ACCEPT + REJECT
    assert node_results(texts, flags) == [python_accepts(t) for t in texts]
    assert node_results(ACCEPT, flags) == [True] * len(ACCEPT)
    assert node_results(REJECT, flags) == [False] * len(REJECT)


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_every_character_agrees_between_python_and_javascript():
    texts = [f"a{chr(c)}a" for c in range(0x20, 0x10000) if not 0xD800 <= c <= 0xDFFF]
    expected = [python_accepts(t) for t in texts]
    results = []
    for start in range(0, len(texts), 20000):
        results += node_results(texts[start:start + 20000], "")
    assert results == expected


def test_the_pattern_never_accepts_what_the_server_refuses():
    # Crop's rule is the server check. The pattern may be stricter (it lists the
    # letters of the Unicode version it was written with, so a letter added
    # since is refused in the browser and accepted by the server) but it must
    # not let through what the server then refuses.
    wrong = [hex(c) for c in range(0x20, 0x10000)
             if not 0xD800 <= c <= 0xDFFF and python_accepts(f"a{chr(c)}a") and name_rules.name_issue(f"a{chr(c)}a")]
    assert wrong == []


def test_the_pattern_is_stricter_only_for_letters_newer_than_it():
    newer = [c for c in range(0x20, 0x10000)
             if not 0xD800 <= c <= 0xDFFF and not python_accepts(f"a{chr(c)}a") and name_rules.name_issue(f"a{chr(c)}a") is None]
    assert all(unicodedata.category(chr(c)).startswith(("L", "M")) for c in newer)
    assert len(newer) < 20


@pytest.mark.parametrize("text", ACCEPT)
def test_server_accepts(text):
    assert name_rules.name_issue(text) is None


@pytest.mark.parametrize("text", [t for t in REJECT if t not in ("", "  ")] + [None, 12])
def test_server_rejects(text):
    assert name_rules.name_issue(text)


def test_server_rejects_blank_names_but_the_record_check_leaves_them_to_the_form():
    assert name_rules.name_issue("") == "letters"
    assert name_rules.name_issue("   ") == "letters"
    assert name_rules.name_problems({"first_name": "", "middle_name": "  ", "last_name": None}) == []


def test_message_is_readable():
    assert name_rules.name_problems({"first_name": "E2E Test"}) == [
        "First Name: use letters only (spaces, apostrophes and hyphens allowed)"]
    assert name_rules.name_problems({"middle_name_local": "Abebe1", "last_name": "Kebede"}) == [
        "Father's Name (own language): use letters only (spaces, apostrophes and hyphens allowed)"]
    assert name_rules.name_problems({"last_name": "a" * 101}) == [
        "Grandfather's Name: too long. Enter at most 100 characters"]
    assert name_rules.name_problems({"first_name": "Abebe", "last_name_local": "ቀበደ"}) == []


def test_every_name_field_is_checked():
    record = dict.fromkeys(name_rules.NAME_LABELS, "X1")
    assert len(name_rules.name_problems(record)) == 6


def test_the_seed_applies_the_rule_to_every_name_field_and_has_its_message():
    for field in name_rules.NAME_LABELS:
        assert f"'{field}'" in _SEED
    assert "'patternMessage', 'name_letters_only'" in _SEED
    translations = (_ROOT / "meta_data/zz-oan/30_translations.sql").read_text(encoding="utf-8")
    assert '"name_letters_only":' in translations
    checks = (_ROOT / "meta_data/zz-oan/90_checks.sql").read_text(encoding="utf-8")
    assert "name_letters_only" in checks
