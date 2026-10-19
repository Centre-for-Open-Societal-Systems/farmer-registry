"""Explicit disposable-PostgreSQL check of the pinned intake save/read service.

Run through tests/integration/run-location-livestock.ps1. Never use a deployed DB.
The Master Data dependency is a local HTTP fixture, not a patched HTTP client.
"""
import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie

ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "farmer-extension/src/openg2p_registry_farmer_extension/meta_data/register-metadata"
FARMER = "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd"
LIVESTOCK = "4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb"
FORM = "a1a4d25a-1cd4-4356-abac-8782382649"
LOCATION = "farmer_farmer_location_section_03"
ANIMALS = "farmer_livestock_livestock_details_section_01"
LEVELS = [("region", None, "Oromia"), ("zone", "region", "East Shewa"),
          ("woreda", "zone", "Ada"), ("kebele", "woreda", "Dire 01")]
REQUESTS = []


class MasterDataFixture(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        csrf = self.headers.get("X-CSRF-Token")
        if not csrf or "X-CSRF-Token" not in cookie or cookie["X-CSRF-Token"].value != csrf:
            self.send_error(403, "Matching CSRF header and cookie required")
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        REQUESTS.append(self.path)
        if self.path == "/geo/get_all_geo_levels":
            payload = [{"level_id": level, "level_mnemonic": level,
                        "parent_level_id": parent} for level, parent, _ in LEVELS]
        elif self.path == "/geo/get_geo_level_values":
            level = body["request_body"]["request_payload"]["level_id"]
            payload = [{"level_id": item, "level_value_id": item + "-test",
                        "level_value_mnemonic": name,
                        "parent_level_value_id": parent + "-test" if parent else None}
                       for item, parent, name in LEVELS if item == level]
        elif self.path == "/attributes/get_attribute_values":
            payload = {"attribute_values": [], "total": 0}
        else:
            self.send_error(501)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"response_header": {"response_status": "SUCCESS"},
                                    "response_body": {"response_payload": payload}}).encode())


async def main():
    # No caller-controlled URL: this runner is isolated on its own Docker network.
    from sqlalchemy import select, text, func
    from sqlalchemy.ext.asyncio import create_async_engine
    from openg2p_fastapi_common.context import dbengine
    from openg2p_fastapi_common.models import BaseORMModel
    from openg2p_registry_core.errors import G2PRegistryException
    from openg2p_registry_core.helpers.master_data import MasterDataClient
    from openg2p_registry_core.services import (
        G2PAttributeValueValidator, G2PDocumentService, G2PGeoHierarchyService,
        G2PIntakeFormDataService, G2PIntakeFormLinkService,
    )
    from openg2p_registry_core.models import G2PIntakeFormSubmission
    from openg2p_registry_farmer_extension.register_domain.models import (
        G2PIntakeFormFarmer, G2PIntakeFormLivestock,
    )
    engine = create_async_engine("postgresql+asyncpg://postgres:fixture@farmer-qa-db/postgres")
    dbengine.set(engine)
    MasterDataClient(); G2PAttributeValueValidator(); G2PGeoHierarchyService()
    G2PDocumentService(); G2PIntakeFormLinkService()
    service = G2PIntakeFormDataService()
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.run_sync(BaseORMModel.metadata.create_all)
            raw = (await conn.get_raw_connection()).driver_connection
            for filename in ("g2p_register_definitions.sql", "g2p_intake_form_definitions.sql",
                             "g2p_register_sections.sql", "g2p_intake_form_ui_tabs.sql",
                             "g2p_intake_form_ui_tab_sections.sql", "zz_farmer_location_layout.sql"):
                await raw.execute((META / filename).read_text())
            repair = (META / "zz_livestock_row_validation.sql").read_text()
            # Simulate installed metadata before G2R-334, including an unrelated option.
            old = await conn.scalar(text("SELECT section_ui_schema FROM g2p_register_sections WHERE section_id=:section"), {"section": ANIMALS})
            old["custom-preservation-marker"] = True
            old_columns = old["panels"][0]["panels"][0]["widgets"][0]["widget-data-columns"]
            for column in old_columns:
                column.pop("widget-required", None)
                if column["column-key"] == "head_count":
                    column["widget-data-validation"].pop("max", None)
            await raw.execute("UPDATE g2p_register_sections SET section_ui_schema=$1::jsonb WHERE section_id=$2", json.dumps(old), ANIMALS)
            await raw.execute(repair)
            first = await conn.scalar(text("SELECT section_ui_schema FROM g2p_register_sections WHERE section_id=:section"), {"section": ANIMALS})
            await raw.execute(repair)
            second = await conn.scalar(text("SELECT section_ui_schema FROM g2p_register_sections WHERE section_id=:section"), {"section": ANIMALS})
            assert first == second and first["custom-preservation-marker"] is True
            columns = first["panels"][0]["panels"][0]["widgets"][0]["widget-data-columns"]
            assert {c["column-key"] for c in columns if c.get("widget-required")} == {"livestock_type", "head_count"}

        async def save(section, register, rows, submission_id=None):
            return await service.save_intake_form_submission(submission_id, section, rows,
                register, FORM, FARMER, "Synthetic QA")

        response = await save(LOCATION, FARMER, [{"latitude": "0", "longitude": "38.7469",
            "language_spoken": "AMHARIC", "local_language": "AFAAN_OROMO",
            "geo_lowest_level_value_id": "kebele-test"}])
        submission_id = response.submission_id
        records = [record for section in response.section_payloads for record in section.records
                   if section.section_register_id == FARMER]
        row = records[0]
        internal_id = row["internal_record_id"]
        assert row["latitude"] == 0 and row["longitude"] == 38.7469
        assert row["region_name"] == "Oromia" and row["zone_name"] == "East Shewa"
        assert row["language_spoken"] == "AMHARIC" and row["local_language"] == "AFAAN_OROMO"
        assert len(row["geo_code_hierarchy_json"]["hierarchy"]) == 4
        await save("farmer_farmer_personal_identification_section_01", FARMER,
                   [{"internal_record_id": internal_id, "first_name": "Syntheticqa"}], submission_id)
        response = await service.get_intake_form_submission(submission_id)
        row = next(record for section in response.section_payloads for record in section.records
                   if section.section_register_id == FARMER)
        assert row["latitude"] == 0 and row["language_spoken"] == "AMHARIC"
        assert row["region_name"] == "Oromia" and row["zone_name"] == "East Shewa"

        from openg2p_fastapi_common.context import get_async_session_maker
        async def count(model):
            async with get_async_session_maker()() as session:
                return await session.scalar(select(func.count()).select_from(model))
        before = await count(G2PIntakeFormSubmission)
        try:
            await save(ANIMALS, LIVESTOCK, [{}])
        except G2PRegistryException as error:
            assert "Livestock Type" in str(error)
        else:
            raise AssertionError("Blank livestock row saved")
        assert await count(G2PIntakeFormSubmission) == before
        assert await count(G2PIntakeFormLivestock) == 0
        await save(ANIMALS, LIVESTOCK, [{"livestock_type": "CATTLE", "head_count": 0}], submission_id)
        assert await count(G2PIntakeFormLivestock) == 1
        # A valid first row plus invalid second row must roll back as a unit.
        try:
            await save(ANIMALS, LIVESTOCK, [{"livestock_type": "GOAT", "head_count": 2}, {}], submission_id)
        except G2PRegistryException:
            pass
        else:
            raise AssertionError("Partially valid table saved")
        assert await count(G2PIntakeFormLivestock) == 1
        response = await service.get_intake_form_submission(submission_id)
        animals = [record for section in response.section_payloads for record in section.records
                   if section.section_register_id == LIVESTOCK]
        assert animals[0]["livestock_type"] == "CATTLE" and animals[0]["head_count"] == 0
        await save(ANIMALS, LIVESTOCK, [], submission_id)
        assert await count(G2PIntakeFormLivestock) == 0
        assert "/geo/get_all_geo_levels" in REQUESTS and "/geo/get_geo_level_values" in REQUESTS
        print("PASS: Location save/read/later-section preservation; livestock atomic rejection/zero/empty; idempotent metadata; real Master Data HTTP")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    fixture = ThreadingHTTPServer(("127.0.0.1", 0), MasterDataFixture)
    os.environ["REGISTRY_CORE_MASTER_DATA_API_URL"] = "http://127.0.0.1:" + str(fixture.server_port)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    sys.modules["openg2p_registry_extensions"] = importlib.import_module("openg2p_registry_farmer_extension")
    for part in ("register_domain", "register_domain.models", "register_domain.schemas", "register_domain.services"):
        sys.modules["openg2p_registry_extensions." + part] = importlib.import_module("openg2p_registry_farmer_extension." + part)
    try:
        asyncio.run(main())
    finally:
        fixture.shutdown()
