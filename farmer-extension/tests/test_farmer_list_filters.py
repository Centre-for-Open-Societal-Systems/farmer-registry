"""The farmer list's filters and result columns (zz-oan/05_registers.sql), read
from the seed itself, so they run without the registry installed.

Core's FilterBuilder accepts at most 10 filter fields, its filter types are
fixed, and a filter on a column the Farmer model does not map is dropped."""

import json
import re
from pathlib import Path

SRC = Path(__file__).parents[1] / "src/openg2p_registry_farmer_extension"
SEED = (SRC / "meta_data/zz-oan/05_registers.sql").read_text(encoding="utf-8")
FIELDS = (SRC / "register_domain/fields.py").read_text(encoding="utf-8")
CORE_FILTER_TYPES = {"dropdown", "text", "date_range", "number_range", "boolean"}
# Columns of the upstream farmer table and core's register mixin used here.
UPSTREAM_COLUMNS = {"first_name", "last_name", "gender", "birth_date", "registration_date", "record_status"}


def _filter_schema():
    match = re.search(r"""SET "filter_schema" = '(\[.*?\])'::json\s+WHERE "register_id" = 'a1a4d25a-""", SEED, re.DOTALL)
    assert match, "the Farmer filter_schema is written out in 05_registers.sql"
    return json.loads(match.group(1).replace("''", "'"))


def _oan_farmer_field(name):
    return re.search(rf'^\s+"{name}": \(', FIELDS, re.MULTILINE) is not None


def test_the_farmer_list_filters():
    schema = _filter_schema()
    assert [f["field_name"] for f in sorted(schema, key=lambda f: f["order"])] == [
        "first_name", "last_name", "gender", "birth_date", "region_name", "zone_name", "woreda_name",
        "kebele_name", "registration_date", "record_status"]
    assert len(schema) <= 10
    by_name = {f["field_name"]: f for f in schema}
    assert by_name["record_status"]["display_label"] == "Status"
    assert by_name["registration_date"]["filter_type"] == "date_range"
    assert "between" in by_name["registration_date"]["allowed_operators"]
    for level in ("region", "zone", "woreda", "kebele"):
        assert by_name[f"{level}_name"]["display_label"] == level.title()
        assert by_name[f"{level}_name"]["filter_type"] == "text"


def test_every_filter_is_a_core_type_on_a_mapped_column():
    for field in _filter_schema():
        assert field["filter_type"] in CORE_FILTER_TYPES, field
        assert 1 <= len(field["allowed_operators"]) and field["display_label"].strip()
        assert "_" not in field["display_label"], field
        name = field["field_name"]
        assert name in UPSTREAM_COLUMNS or _oan_farmer_field(name), name


def test_the_list_shows_land_plots_and_mobile_number():
    for name, label in (("total_land_area", "Total land (hectares)"), ("total_plots", "Total plots"),
                        ("primary_phone_number", "Mobile number")):
        assert f"'{name}', '{label}'" in SEED, name
    assert _oan_farmer_field("total_plots") and _oan_farmer_field("primary_phone_number")
