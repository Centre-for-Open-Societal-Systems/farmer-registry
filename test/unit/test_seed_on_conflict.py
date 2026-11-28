"""Guard: every INSERT the seed runs has an ON CONFLICT clause.

The db-seed image (docker/db-seed/Dockerfile) copies meta_data/ and awe_meta_data/ and replays them on every install
and upgrade. An INSERT without ON CONFLICT fails the second run on its primary key, or, on a table without one,
inserts the rows again. Comments and string literals are masked first, so a semicolon or the words ON CONFLICT
inside a literal neither split a statement nor satisfy the check.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "farmer-extension/src/openg2p_registry_farmer_extension"
SEED_DIRS = ("meta_data", "awe_meta_data")
COMMENT_OR_LITERAL = re.compile(r"--[^\n]*|/\*.*?\*/|'(?:[^']|'')*'", re.S)


def inserts():
    """(file, statement) for every INSERT in the seed SQL."""
    for path in sorted(p for d in SEED_DIRS for p in (EXT / d).rglob("*.sql")):
        sql = COMMENT_OR_LITERAL.sub(lambda m: "''" if m.group().startswith("'") else " ", path.read_text())
        for statement in sql.split(";"):
            for match in re.finditer(r"\bINSERT\s+INTO\b", statement, re.I):
                yield path.relative_to(EXT).as_posix(), statement[match.start():]


def test_every_seed_insert_has_on_conflict():
    found = list(inserts())
    assert len(found) > 50, "Too few INSERTs found; has the seed moved?"
    missing = [(name, " ".join(statement.split())[:120]) for name, statement in found
               if not re.search(r"\bON\s+CONFLICT\b", statement, re.I)]
    assert not missing, missing
