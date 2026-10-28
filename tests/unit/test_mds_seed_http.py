"""Run the real seed HTTP client against the local Postman contract."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docker/db-seed"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_mds_sample_seed import fixtures
import master_data_samples as source
import load_sample_data as loader

BASE = os.environ.get("OAN_SEED_SIMULATION_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="Requires Postman seed simulation")


def test_mds_people_submit_native_sections_without_fabricated_assets():
    _, before = loader.http_json("GET", BASE + "/records")
    previous = {row["id"] for row in before["response_body"]["response_payload"]}
    _, households = source.adapt_samples(*fixtures())
    loader._GEO_BY_ID = {"ET01010102": ("kebele", "Test", None)}
    client = loader.StaffClient(BASE, "simulation-token", "seed-user")
    _, household_id = loader.submit_household(client, households[0])
    _, farmer_id = loader.submit_farmer(client, households[0], household_id, 0)
    assert household_id and farmer_id
    status, body = loader.http_json("GET", BASE + "/records")
    assert status == 200
    records = [row for row in body["response_body"]["response_payload"] if row["id"] not in previous]
    assert len(records) == 2 and all(row["finalized"] for row in records)
    sections = [s["section_id"] for row in records for s in row["sections"]]
    assert loader.FARMER_PERSONAL_SECTION in sections
    assert loader.FARMER_LAND_SECTION not in sections
    assert loader.FARMER_CROP_SECTION not in sections
    assert loader.FARMER_LIVESTOCK_SECTION not in sections


def test_invalid_prefix_label_is_rejected_over_real_http():
    client = loader.StaffClient(BASE, "simulation-token", "seed-user")
    with pytest.raises(RuntimeError, match="422"):
        loader.save_section(client, submission_id=None, section_id=loader.FARMER_PERSONAL_SECTION,
            section_register_id=loader.FARMER_REGISTER_ID, form_id=loader.FARMER_FORM_ID,
            register_id=loader.FARMER_REGISTER_ID, records=[{"prefix":"Mr"}])
