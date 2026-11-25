"""Guard: every field name the metadata, templates and reporting views use is a column of the model.

A field name that does not match a column fails silently: the platform saves nothing for a widget bound to a
missing column, a search or filter on it finds nothing, and a reporting view breaks only when it is refreshed in
a cluster. ci/validation/check_native_metadata.py replays the seed in a disposable PostgreSQL; this test reads the
same files statically, so it needs no database or platform image and runs on every push in under a second.

The model's columns are read from source with ast, without importing it:
  * the farmer extension's mixins (openg2p_farmer/register_domain/models/*.py) and OAN's farmer phone register
  * OAN's added columns (register_domain/fields.py, OAN_FIELDS)
  * the platform base classes the registers inherit from (CORE_COLUMNS below)
"""

import ast
import re
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "farmer-extension/src/openg2p_registry_farmer_extension"
NATIVE_MODELS = EXT / "openg2p_farmer/register_domain/models"
OAN_MODELS = EXT / "register_domain/models"

# The platform base classes' columns (openg2p_registry_core.models, g2p_register.py and
# g2p_register_authentication.py) at the pinned platform version. When scripts/bump-rp-version.sh moves the pin,
# compare these with the new version's core models and update CORE_VERSION.
CORE_VERSION = "1.2.2-rc.625"
CORE_COLUMNS = {
    "G2PRegister": {
        "internal_record_id", "functional_record_id", "link_internal_record_id", "link_foundational_id",
        "record_name", "record_image_document_id", "created_by", "created_at", "last_approved_at",
        "last_approved_by", "search_text", "record_status", "record_status_reason"},
    "G2PPerson": {
        "foundational_id", "first_name", "middle_name", "last_name", "given_name", "prefix", "suffix", "gender",
        "birth_date", "phone_numbers", "emails", "marital_status", "occupation", "income_level", "language_code",
        "education_level", "registration_date"},
    "G2PGeo": {
        "latitude", "longitude", "altitude", "plus_code", "address_line_1", "address_line_2", "postal_code",
        "country_code", "geo_lowest_level_value_id", "geo_code_hierarchy_json"},
    "G2PGeoShape": {"shape_type", "shape_coordinates_json"},
    "G2PRegisterAuthentication": {
        "last_authentication_id", "last_authenticated_at", "last_authentication_status", "authentication_expiry_at",
        "authentication_expiry_notified", "authentication_token"},
}


@cache
def models():
    """{register mnemonic: columns} and {table name: register mnemonic}, read from the model source."""
    mixins, registers, tables = {}, {}, {}
    for path in sorted(NATIVE_MODELS.glob("*.py")) + [OAN_MODELS / "farmer_phone.py"]:
        for node in ast.parse(path.read_text()).body:
            if not isinstance(node, ast.ClassDef):
                continue
            columns = {s.target.id for s in node.body if isinstance(s, ast.AnnAssign)
                       and isinstance(s.value, ast.Call) and getattr(s.value.func, "id", None) == "mapped_column"}
            bases = [ast.unparse(b) for b in node.bases]
            if not bases:
                mixins[node.name] = columns
            elif node.name.startswith("G2PRegister") and not node.name.startswith("G2PRegisterHistory"):
                mnemonic = node.name.removeprefix("G2PRegister")
                registers[mnemonic] = columns.union(*(CORE_COLUMNS.get(b, mixins.get(b, set())) for b in bases))
                for s in node.body:
                    if isinstance(s, ast.Assign) and getattr(s.targets[0], "id", None) == "__tablename__":
                        tables[s.value.value] = mnemonic
    for node in ast.parse((EXT / "register_domain/fields.py").read_text()).body:
        if isinstance(node, ast.AnnAssign) and node.target.id == "OAN_FIELDS":
            for mnemonic, fields in zip(node.value.keys, node.value.values):
                registers[mnemonic.value] |= {f.value for f in fields.keys}
    # register_domain/models/__init__.py puts core's registrant authentication mixin on the farmer.
    registers["Farmer"] |= CORE_COLUMNS["G2PRegisterAuthentication"]
    return registers, tables


def columns(mnemonic):
    return models()[0][mnemonic]


def test_core_columns_follow_the_platform_pin():
    pin = re.search(r"^ARG BASE_IMAGE_VERSION=(\S+)$", (ROOT / "docker/staff-api/Dockerfile").read_text(), re.M)
    assert pin and pin.group(1) == CORE_VERSION, "Platform pin moved: re-check CORE_COLUMNS against its core models"


def test_model_source_yields_every_register():
    registers, tables = models()
    assert set(registers) == {
        "Farmer", "FarmerPhone", "Household", "HouseholdMember", "Land", "Crop", "Livestock", "FarmInputs",
        "MembershipDetails"}
    assert {"g2p_register_farmers", "g2p_register_lands", "g2p_register_crops"} <= set(tables)
    assert {"internal_record_id", "first_name", "latitude", "income_sources", "last_authenticated_at"} \
        <= columns("Farmer")
