"""Guard: every /seed file the chart's jobs run must be copied into the db-seed image.

Those jobs run inside the db-seed image, so a file they name but the image does
not ship only fails at deploy time, as a hook Job in BackoffLimitExceeded after
the build and push have already succeeded. Files the chart's templates name under
/seed/ are this registry's own, so each must be COPYed in BOTH db-seed
definitions: the root Dockerfile's db-seed stage (what Jenkins builds) and
docker/db-seed/Dockerfile.

No dependencies beyond the stdlib + pytest.
"""

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = REPO / "helm" / "openg2p-farmer-registry" / "templates"


def _referenced():
    found = set()
    for f in TEMPLATES.glob("*.yaml"):
        found.update(re.findall(r"/seed/([A-Za-z0-9_.-]+)", f.read_text()))
    return sorted(found)


def _root_db_seed_stage():
    text = (REPO / "Dockerfile").read_text()
    m = re.search(r"^FROM \S+ AS db-seed\s*$(.*?)(?=^FROM |\Z)", text, re.M | re.S)
    assert m, "root Dockerfile has no db-seed stage"
    return m.group(1)


def _copied(dockerfile_text):
    return set(re.findall(r"^COPY\s+\S+\s+/seed/([A-Za-z0-9_.-]+)\s*$", dockerfile_text, re.M))


def test_templates_name_seed_files():
    assert _referenced(), "no /seed/ references found; the regex no longer matches the templates"


@pytest.mark.parametrize("name", _referenced())
def test_root_dockerfile_ships(name):
    assert name in _copied(_root_db_seed_stage()), f"root Dockerfile db-seed stage does not COPY /seed/{name}"


@pytest.mark.parametrize("name", _referenced())
def test_db_seed_dockerfile_ships(name):
    text = (REPO / "docker" / "db-seed" / "Dockerfile").read_text()
    assert name in _copied(text), f"docker/db-seed/Dockerfile does not COPY /seed/{name}"
