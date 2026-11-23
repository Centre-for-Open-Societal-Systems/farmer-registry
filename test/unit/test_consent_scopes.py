"""Guard: every consent scope id the repository names is one the partner API can release.

At the pinned platform the partner API clamps a DCI search response to the consent's effective data scopes by
matching them against the TOP-LEVEL keys of the rendered search response (openg2p_registry_partner_api,
G2PDciService._clamp_record_fields): any other scope name matches nothing and releases nothing, without an error.
So a valid scope id is a top-level key of templates/farmer_dci_search_response.j2.

The scope ids named here:
  * the shipped catalogue, meta_data/data-scopes/*.json (the Consent Manager policies use these names)
  * the sanity DCI e2e's consented and denied scopes, helm values registry.sanity.dataScopes / deniedScopes, which
    the platform chart passes to the sanity image as SANITY_DATA_SCOPES / SANITY_DENIED_SCOPES
"""

import json
from pathlib import Path

import yaml
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "farmer-extension/src/openg2p_registry_farmer_extension"
VALUES = ROOT / "helm/openg2p-farmer-registry/values.yaml"

# Scope ids that are not top-level keys today. The sanity names are the section scopes of a later platform's data
# scope service (test/integration/test_data_scopes.py); at the pinned platform the sanity image's own defaults are
# farmer_personal_details, denying family_details, farm_details and machineries_details. Remove an entry once its
# scope is corrected: the test fails while a listed gap no longer exists.
KNOWN_INVALID = {
    ("values.yaml registry.sanity.dataScopes", "personal_details"),
    ("values.yaml registry.sanity.deniedScopes", "farmer_identifiers"),
    ("values.yaml registry.sanity.deniedScopes", "contact"),
}


def releasable_scopes():
    template = (EXT / "templates/farmer_dci_search_response.j2").read_text(encoding="utf-8")
    return set(json.loads(Environment().from_string(template).render(expanded={})))


def named_scopes():
    """(where, scope id) for every consent scope id the repository names."""
    for path in sorted((EXT / "meta_data/data-scopes").glob("*.json")):
        for scope in json.loads(path.read_text(encoding="utf-8"))["scopes"]:
            yield f"data-scopes/{path.name}", scope["name"]
    sanity = yaml.safe_load(VALUES.read_text(encoding="utf-8"))["registry"]["sanity"]
    for key in ("dataScopes", "deniedScopes"):
        for scope in str(sanity.get(key) or "").split(","):
            if scope.strip():
                yield f"values.yaml registry.sanity.{key}", scope.strip()


def test_consent_scope_ids_are_releasable():
    releasable = releasable_scopes()
    assert {"farmer_personal_details", "farmer_reference"} <= releasable, releasable
    named = set(named_scopes())
    assert ("data-scopes/farmer_reference.json", "farmer_reference") in named
    invalid = {(where, scope) for where, scope in named if scope not in releasable}
    assert invalid == KNOWN_INVALID, {"new": sorted(invalid - KNOWN_INVALID),
                                      "fixed, remove from KNOWN_INVALID": sorted(KNOWN_INVALID - invalid)}
