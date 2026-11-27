"""Verify Farmer intake photo and document metadata limits in zz-oan seeds.

Run by CI in the contracts job via ``ci/validation/validate.sh``
(``pytest test/unit``).
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ZZ_OAN = REPO / "farmer-extension/src/openg2p_registry_oan_farmer_extension/meta_data/zz-oan"


def _sql_jsonb(sql_text: str, marker: str):
    start = sql_text.index(marker)
    quote_start = sql_text.rindex("'", 0, start)
    end = sql_text.index("'::jsonb", start)
    return json.loads(sql_text[quote_start + 1 : end].replace("''", "'"))


def test_farmer_photo_metadata_limits():
    sql = (ZZ_OAN / "10_sections.sql").read_text(encoding="utf-8")
    section = _sql_jsonb(sql, '"section-id": "farmer_photo"')
    widgets = [w for panel in section["panels"] for w in panel["widgets"]]
    photo = next(w for w in widgets if w.get("widget-variant") == "oan-farmer-photo")

    assert photo["widget-data-format"]["maxDimension"] == 750
    assert photo["widget-data-format"]["aspectRatio"] == "4:5"
    assert photo["widget-data-validation"]["maxSizeKb"] == 100


def test_land_certificate_metadata_limits():
    sql = (ZZ_OAN / "10_sections.sql").read_text(encoding="utf-8")
    columns = _sql_jsonb(sql, '"column-key": "certificate_storage_id"')
    cert = next(c for c in columns if c.get("column-key") == "certificate_storage_id")

    assert cert["widget-data-options"]["maxSize"] == 2 * 1024 * 1024


def test_farmer_documents_max_size():
    sql = (ZZ_OAN / "12_form_sections.sql").read_text(encoding="utf-8")
    match = re.search(
        r"doc_settings\s*\([^)]+\)\s*AS\s*\(\s*VALUES\s*\(\s*(\d+)\s*,\s*'([^']+)'\s*,\s*(\d+)\s*\)",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, "doc_settings CTE not found in 12_form_sections.sql"
    slots, accept, max_size = int(match.group(1)), match.group(2), int(match.group(3))

    assert slots == 5
    assert set(accept.split(",")) == {".pdf", ".jpg", ".jpeg", ".png"}
    assert max_size == 2 * 1024 * 1024
