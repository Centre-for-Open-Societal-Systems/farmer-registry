"""OpenG2P's Farmer extension is the installed dependency the OAN package builds on.

The OAN package (openg2p_registry_oan_farmer_extension) re-exports OpenG2P's openg2p_registry_farmer_extension and
redefines the classes OAN extends under the same names; the platform selects the OAN package through
REGISTRY_EXTENSION_MODULE. Run where the platform and both distributions are installed (the staff-api image).
"""
import importlib
import importlib.metadata
import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

pytest.importorskip("openg2p_registry_core")

ROOT = Path(__file__).resolve().parents[2]
OAN = "openg2p_registry_oan_farmer_extension"
UPSTREAM = "openg2p_registry_farmer_extension"
# The platform publishes the selected extension under this name; upstream's enricher imports through it.
ALIAS = "openg2p_registry_extensions"


def _package_dir(name):
    return Path(importlib.util.find_spec(name).origin).parent


def test_the_upstream_extension_is_its_own_installed_distribution():
    distribution = importlib.metadata.distribution("openg2p-registry-farmer-extension")
    assert distribution.version == "1.0.3"
    upstream = _package_dir(UPSTREAM)
    assert upstream != _package_dir(OAN)
    assert _package_dir(OAN) not in upstream.parents
    assert importlib.import_module(UPSTREAM).__variant__ == "farmer"


def test_the_installed_upstream_extension_is_the_published_tree():
    """The wheel the image built from the pinned commit holds sample-farmer-extension/'s package, byte for byte."""
    published = ROOT / "sample-farmer-extension/src" / UPSTREAM
    expected = {p.relative_to(published).as_posix(): p.read_bytes()
                for p in published.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    distribution = importlib.metadata.distribution("openg2p-registry-farmer-extension")
    installed = {}
    for file in distribution.files:
        parts = Path(file).parts
        if parts[0] == UPSTREAM and "__pycache__" not in parts:
            installed[Path(*parts[1:]).as_posix()] = Path(distribution.locate_file(file)).read_bytes()
    assert sorted(installed) == sorted(expected)
    changed = sorted(name for name in expected if installed[name] != expected[name])
    assert changed == [], changed


def test_the_upstream_extension_is_the_1_0_3_baseline():
    """The pinned commit is 1.0.3's: the household check OAN wraps is there, and the farmer still
    carries the disability columns that 1.2 moves to farmer_disability."""
    importlib.import_module(f"{UPSTREAM}.register_domain.services.household_submission_validation")
    farmer = importlib.import_module(f"{UPSTREAM}.register_domain.models.farmer").G2PFarmer
    assert {"disability_type", "disability_severity"} <= set(farmer.__annotations__)
    assert importlib.util.find_spec(f"{UPSTREAM}.register_domain.models.farmer_disability") is None


def test_the_oan_initializer_runs_upstreams_first():
    upstream = importlib.import_module(f"{UPSTREAM}.app").Initializer
    oan = importlib.import_module(f"{OAN}.app").Initializer
    assert issubclass(oan, upstream) and oan is not upstream


@pytest.mark.parametrize("module", [
    "config", "register_domain.models", "register_domain.schemas", "register_domain.services",
    "register_domain.id_generator", "ingestion_pipeline.enricher_services", "score_compute.services",
])
def test_every_platform_module_of_the_oan_package_re_exports_upstreams_names(module, monkeypatch):
    if ALIAS not in sys.modules:
        monkeypatch.setitem(sys.modules, ALIAS, importlib.import_module(OAN))
    upstream = importlib.import_module(f"{UPSTREAM}.{module}")
    oan = importlib.import_module(f"{OAN}.{module}")
    public = {name for name, value in vars(upstream).items()
              if not name.startswith("_") and not inspect.ismodule(value)}
    missing = sorted(name for name in public if not hasattr(oan, name))
    assert missing == [], missing
