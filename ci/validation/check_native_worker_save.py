"""Hosted-only native worker save/rollback proof; never FINAL or a queued task."""
from __future__ import annotations

import argparse
import asyncio
import json
import inspect
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[2]


def initialize(host):
    import importlib.metadata
    os.environ.setdefault("REGISTRY_CELERY_WORKERS_WORKER_QUEUE", "owned-native-save-probe")
    main = importlib.import_module("openg2p_registry_celery_worker.main")
    app = main.celery_app
    extra = [x.strip() for x in os.environ.get("CELERY_IMPORTS", "").split(",") if x.strip()]
    assert extra == ["openg2p_registry_extensions.worker"]
    app.conf.update(include=list(app.conf.include or []) + extra)
    app.loader.import_default_modules()
    # Native workers load domain models lazily; DDL setup must explicitly
    # register the selected extension ORM, without constructing an API app.
    importlib.import_module("openg2p_registry_extensions.register_domain.models")
    from openg2p_registry_celery_worker.engine import Engine
    from openg2p_registry_celery_worker.config import Settings
    import openg2p_registry_extensions
    assert not str(openg2p_registry_extensions.__file__).startswith("/repo/")
    assert Engine.get_engine().url.host == host
    assert Engine.get_engine().url.database == "native_worker_save"
    task = importlib.import_module("openg2p_registry_celery_worker.tasks.ingest_data_worker")
    assert task._session_maker is Engine.get_async_session_maker()
    from openg2p_registry_core.services.intake_form_data_service import G2PIntakeFormDataService
    from openg2p_registry_extensions.register_domain.services.household_intake import OANIntakeFormDataService
    assert isinstance(G2PIntakeFormDataService.get_component(), OANIntakeFormDataService)
    from openg2p_registry_core.interfaces import G2PRegisterDomainFactory
    services = importlib.import_module("openg2p_registry_extensions.register_domain.services")
    factory = G2PRegisterDomainFactory.get_component()
    identities = {}
    for mnemonic in ("Farmer", "Crop", "Land"):
        service = factory.get_domain_service(mnemonic)
        expected = getattr(services, "G2PRegisterDomainService" + mnemonic)
        actual = type(service)
        identities[mnemonic] = {"actual": actual.__module__ + "." + actual.__qualname__,
            "expected": expected.__module__ + "." + expected.__qualname__,
            "domain_validator_owner": service.validate_domain_attributes.__func__.__module__ + "." + service.validate_domain_attributes.__func__.__qualname__}
        expect(actual is expected, True, "native domain factory " + mnemonic)
    print(json.dumps({"native_domain_factory": identities}), flush=True)
    installed = {}
    for name in ("save_intake_form_submission_with_session", "_upsert_intake_rows"):
        method = getattr(G2PIntakeFormDataService, name)
        source = inspect.getsource(method)
        installed[name] = {"module": method.__module__, "qualname": method.__qualname__,
            "sha256": hashlib.sha256(source.encode()).hexdigest(), "source": source}
    print(json.dumps({"installed_native_intake_callables": installed}), flush=True)
    package_names = ("openg2p-registry-core", "openg2p-registry-celery-worker", "openg2p-registry-farmer-extension")
    packages = {name: importlib.metadata.version(name) for name in package_names}
    contract = json.loads((ROOT / "ci/validation/native-release-contract.json").read_text(encoding="utf-8"))
    assert packages == contract["observedInstalledPackages"], "Installed native package contract changed without review"
    print(json.dumps({"initializer": "native worker.main + CELERY_IMPORTS", "native_engine_preserved": True,
        "validate_attribute_values": Settings.get_config().validate_attribute_values,
        "packages": packages}), flush=True)
    return Engine, task


def expect(actual, expected, label):
    assert actual == expected, json.dumps({"check": label, "actual": actual, "expected": expected}, default=str, sort_keys=True)


def fixture(document_id):
    lands = [str(uuid.uuid4()), str(uuid.uuid4())]
    return {"basic_info": {"personal_info": {"first_name_english": "Synthetic", "father_name_english": "Worker",
            "grandfather_name_english": "Head", "gender": "male", "date_of_birth": "1980-01-01", "farming_type": "mixed_farming"},
            },
        "socio_economic_data": {"income_source": "crop_production livestock"},
        "household_questions": {"household_head": "yes"},
        "national_id_section": {"national_id": "yes", "national_fin": "009900000123", "identity_document_type": "FAYDA", "identity_document": document_id},
        "other_hh_members": {"other_hh_members_repeat": [{"other_member_name_english": "Synthetic Worker Daughter", "member_gender": "female", "member_dob": "2010-01-01", "household_relationship": "daughter"}]},
        "land_info": {"land_info_repeat": [{"land_id": "P1", "oan_land_id": lands[0], "land_ownership": "owner", "total_land_area": 1.0},
                                              {"land_id": "P2", "oan_land_id": lands[1], "land_ownership": "owner", "total_land_area": 2.0}]},
        "crop_information": {"crop_repeat": [{"crop_name": "wheat", "crop_season": "meher", "land_id": "P1"},
                                                {"crop_name": "maize", "crop_season": "belg", "land_id": "P2"}],
                             "crop_water_source": "rainfall irrigation_ground"},
        "farm_input_land_id": "P2", "agricultural_input": {"fertilizer_utilized": "yes", "pesticide_utilized": "no"},
        "access_to_resource": {"machinery_access": "yes", "type_of_machinery": "tractor combine_harvester"},
        "access_to_finance": {"finance_access": "yes", "finance": "loan insurance"},
        "livestock_info": {"livestock_repeat": [{"animal": "cattle", "num_animals": 2, "land_id": "P2"}],
                           "livestock_water_source": "well_water surface_water"}}


async def save_probe(Engine, task):
    import importlib
    from datetime import datetime
    from sqlalchemy import select, text, func
    from openg2p_registry_core.errors import G2PRegistryException
    from openg2p_registry_core.models import G2PRegistryDocument, G2PIntakeFormSectionDocuments, G2PIntakeFormSubmission
    from openg2p_registry_extensions.register_domain.models import (
        G2PIntakeFormFarmer, G2PIntakeFormLand, G2PIntakeFormCrop, G2PIntakeFormFarmInputs,
        G2PIntakeFormLivestock, G2PIntakeFormHousehold, G2PIntakeFormHouseholdMember)
    from openg2p_registry_extensions.odk.transform import SECTIONS, intake_sections
    from openg2p_registry_core.interfaces import G2PRegisterDomainFactory
    from openg2p_registry_extensions.register_domain.services.widget_rules import collect_rules
    services = importlib.import_module("openg2p_registry_extensions.register_domain.services")
    maker = Engine.get_async_session_maker()
    assert task._session_maker is maker
    async with maker() as session:
        binding = (await session.execute(text("SELECT register_id,intake_form_id FROM incoming_model_semantic_patterns WHERE data_model_id='FARMER_ODK_MODEL'"))).one()
        classified = SimpleNamespace(register_id=binding[0], intake_form_id=binding[1], partner_id=None)
        sections = await task._get_ordered_form_sections(classified.intake_form_id, session)
        expect([s.section_mnemonic for s in sections], list(SECTIONS), "ordered native section binding")
        finance_section = next(section for section in sections if section.section_mnemonic == SECTIONS[12])
        seeded_rules = collect_rules((section.section_register_id, section.section_ui_schema) for section in sections)
        finance_rule = seeded_rules.get(finance_section.section_register_id, {}).get("finance_access_types")
        farm_inputs_service = G2PRegisterDomainFactory.get_component().get_domain_service("FarmInputs")
        expect(type(farm_inputs_service), services.G2PRegisterDomainServiceFarmInputs, "native FarmInputs domain factory")
        print(json.dumps({"seeded_finance_diagnostic": {
            "section_id": finance_section.section_id, "section_register_id": finance_section.section_register_id,
            "rule": finance_rule, "domain_mnemonic": farm_inputs_service.register_mnemonic(),
            "domain_validator": farm_inputs_service.validate_domain_attributes.__func__.__qualname__,
            "cache_loaded_before_save": bool(services._cache["at"]),
        }}), flush=True)
    from openg2p_fastapi_common.models import BaseORMModel
    async def counts():
        async with maker() as session:
            return {name: await session.scalar(select(func.count()).select_from(table))
                    for name, table in sorted(BaseORMModel.metadata.tables.items())}
    baseline = await counts()
    for scenario in ("valid", "invalid_parent", "invalid_finance"):
        async with maker() as session:
            document_id = str(uuid.uuid4())
            for ident in (document_id, str(uuid.uuid4())):
                session.add(G2PRegistryDocument(document_id=ident, document_store_id="synthetic-" + ident, bucket="documents",
                    source_filename="synthetic.jpg", created_by="synthetic-probe", created_at=datetime(2026, 10, 26)))
            await session.flush()
            source = fixture(document_id)
            data = intake_sections(source)
            if scenario == "invalid_parent":
                data[SECTIONS[11]][1]["link_internal_record_id"] = str(uuid.uuid4())
            elif scenario == "invalid_finance":
                # JSON has no database enum constraint: rejection must come
                # through the real registered OAN schema/domain save path.
                data[SECTIONS[12]][0]["finance_access_types"] = ["LOAN", "OAN_INVALID_FINANCE_CODE"]
            transformed = task._validate_transformed_data_json(classified, SimpleNamespace(transformed_data_json=data), sections)
            submission_id = await task._create_submission_async(classified, session)
            try:
                await task._save_sections_async(submission_id, classified, sections, transformed, session)
            except Exception as error:
                await session.rollback()
                if scenario == "valid":
                    raise
                message = str(getattr(error, "message", error)).lower()
                if scenario == "invalid_parent":
                    assert "land" in message, "Failure did not identify the invalid child land"
                    print(json.dumps({"late_invalid_child_rejected": True, "parent_link_validation_exercised": True, "coded_attribute_validation_exercised": False}), flush=True)
                else:
                    assert isinstance(error, G2PRegistryException), "Expected a domain validation rejection for invalid finance"
                    assert "financ" in message, "Failure did not identify the invalid finance choice"
                    print(json.dumps({"invalid_static_finance_rejected": True, "oan_domain_rule_exercised": True,
                        "coded_attribute_validation_exercised": False}), flush=True)
            else:
                expect(scenario, "valid", "invalid scenario must be rejected by native save")
                async def rows(model):
                    return list((await session.execute(select(model).where(model.submission_id == submission_id))).scalars())
                farmer, = await rows(G2PIntakeFormFarmer)
                lands = await rows(G2PIntakeFormLand)
                crops = await rows(G2PIntakeFormCrop)
                inputs, = await rows(G2PIntakeFormFarmInputs)
                animal, = await rows(G2PIntakeFormLivestock)
                household, = await rows(G2PIntakeFormHousehold)
                members = await rows(G2PIntakeFormHouseholdMember)
                docs = await rows(G2PIntakeFormSectionDocuments)
                mapping = {land.land_id: str(land.internal_record_id) for land in lands}
                expect((len(lands), len(crops)), (2, 2), "persisted parent and crop counts")
                expect({crop.commodity: str(crop.link_internal_record_id) for crop in crops}, {"CROP_BREAD_WHEAT": mapping["P1"], "CROP_MAIZE": mapping["P2"]}, "exact catalogue crop/land links")
                expect((str(inputs.link_internal_record_id), str(animal.link_internal_record_id)), (mapping["P2"], mapping["P2"]), "input and livestock land links")
                expect((farmer.foundational_id, farmer.is_household_head), ("009900000123", True), "Farmer FIN and household head")
                expect((household.size_of_group, household.number_of_male_members, household.number_of_female_members), (2, 1, 1), "household size and gender counts")
                expect((len(members), sum(bool(m.is_head) for m in members)), (2, 1), "household roster and unique head")
                expect(farmer.income_sources, ["SOI_CROP_PRODUCTION", "SOI_LIVESTOCK_PRODUCTION"], "income multi-choice preservation")
                expect((inputs.machinery_types, inputs.finance_access_types), (["MACH_TRACTOR", "MACH_COMBINE"], ["LOAN", "INSURANCE"]), "machinery and finance multi-choice preservation")
                expect((inputs.water_sources, inputs.livestock_water_sources), (["WS_RAINFED", "WS_IRRIGATION_GROUND"], ["WS_WELL_GROUND", "WS_SURFACE_WATER"]), "crop and livestock water multi-choice preservation")
                expect((inputs.machinery_type, inputs.finance_access_type, animal.head_count), (None, None, 2), "no invented singular choices and livestock count")
                expect([(d.document_id, d.label) for d in docs], [(document_id, "identity_document_1")], "scoped identity attachment and unrelated-document exclusion")
                doc_section = next(s.section_id for s in sections if s.section_mnemonic == SECTIONS[15])
                expect(docs[0].section_id, doc_section, "identity attachment section")
                submission = await session.get(G2PIntakeFormSubmission, submission_id)
                expect(submission.draft_status, "DRAFT", "unfinalized submission")
                print(json.dumps({"after_valid_save_diagnostic": {
                    "cache_loaded": bool(services._cache["at"]),
                    "cached_farm_inputs_register": services._cache["registers"].get("FarmInputs"),
                    "cached_finance_rule": services._cache["rules"].get(finance_section.section_register_id, {}).get("finance_access_types"),
                }}), flush=True)
                await session.rollback()
        expect(await counts(), baseline, "all ORM table counts after rollback: " + scenario)
    assert task._session_maker is maker
    print(json.dumps({"native_worker_save": "PASS", "sections": 16, "parents": 2, "rollback": True,
        "late_child_failure_rollback": True, "invalid_static_finance_rollback": True,
        "oan_domain_rule_exercised": True, "native_engine_preserved": True, "finalized": False,
        "awe_called": False, "coded_attribute_validation_exercised": False, "mds_or_filestore_acceptance": "NOT RUN"}), flush=True)


def probe(host, mode):
    Engine, task = initialize(host)
    if mode == "ddl":
        from sqlalchemy import text
        from openg2p_fastapi_common.models import BaseORMModel
        with Engine.get_engine().begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        BaseORMModel.metadata.create_all(Engine.get_engine())
        print(json.dumps({"native_worker_ddl": "PASS", "tables": len(BaseORMModel.metadata.tables)}), flush=True)
    else:
        asyncio.run(save_probe(Engine, task))


def run():
    assert sys.platform == "linux" and os.environ.get("GITHUB_ACTIONS") == "true", "Hosted Linux CI only; no local Docker fallback"
    suffix = uuid.uuid4().hex
    owner = "oan.native-worker-save.owner"
    network_name = "worker-save-" + suffix
    image = os.environ.get("OAN_WORKER_SAVE_TEST_IMAGE", "registry/celery:ci")
    owned = []
    network_id = None
    report = {"verification_complete": False, "live_environment_modified": False, "finalized": False}
    output = ROOT / "ci-output/native-worker-save"
    output.mkdir(parents=True, exist_ok=True)
    def command(*args, data=None, timeout=180):
        result = subprocess.run(args, input=data, capture_output=True, check=False, timeout=timeout)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).decode(errors="replace")[-6000:])
        return result.stdout.decode(errors="replace").strip()
    def create(*args):
        ident = command("docker", "create", "--label", f"{owner}={suffix}", *args)
        owned.append(ident)
        return ident
    def native(mode, database):
        ident = create("--memory=768m", "--network", network_name, "--entrypoint", "python",
            "-v", f"{ROOT.as_posix()}:/repo:ro", "-e", "REGISTRY_CELERY_WORKERS_DB_USERNAME=postgres",
            "-e", "REGISTRY_CELERY_WORKERS_DB_PASSWORD=postgres", "-e", "REGISTRY_CELERY_WORKERS_DB_HOSTNAME=" + database,
            "-e", "REGISTRY_CELERY_WORKERS_DB_DBNAME=native_worker_save", image,
            "/repo/ci/validation/check_native_worker_save.py", "--probe", database, mode)
        log = command("docker", "start", "--attach", ident, timeout=240)
        (output / (mode + ".txt")).write_text(log + "\n", encoding="utf-8")
        assert command("docker", "inspect", ident, "--format", "{{.State.ExitCode}}") == "0", log[-6000:]
        print(log, flush=True)
    try:
        report["source_head"] = command("git", "rev-parse", "HEAD")
        report["image_id"] = command("docker", "image", "inspect", image, "--format", "{{.Id}}")
        network_id = command("docker", "network", "create", "--internal", "--label", f"{owner}={suffix}", network_name)
        database = "worker-save-db-" + suffix
        db = create("--memory=256m", "--name", database, "--network", network_name,
            "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "-e", "POSTGRES_DB=native_worker_save", "postgres:15-alpine")
        command("docker", "start", db)
        for _ in range(120):
            ready = subprocess.run(["docker", "exec", db, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"], capture_output=True, check=False, timeout=10)
            if ready.returncode == 0:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("Owned PostgreSQL did not become ready")
        native("ddl", database)
        files = []
        for domain in ("farmer", "oan"):
            files += sorted((ROOT / f"{domain}-extension/src/openg2p_registry_{domain}_extension/meta_data").rglob("*.sql"))
        for path in files:
            command("docker", "exec", "-i", db, "psql", "-X", "-U", "postgres", "-d", "native_worker_save", "-v", "ON_ERROR_STOP=1", data=path.read_bytes())
        report["seed_sql_files"] = len(files)
        native("save", database)
        report["verification_complete"] = True
    finally:
        failures = []
        for ident in reversed(owned):
            try:
                actual = command("docker", "inspect", ident, "--format", '{{.Id}} {{index .Config.Labels "oan.native-worker-save.owner"}}')
                assert actual == ident + " " + suffix, "Owned container identity mismatch"
                command("docker", "rm", "--force", ident)
            except (AssertionError, RuntimeError, OSError, subprocess.SubprocessError) as error:
                failures.append(type(error).__name__)
        if network_id:
            actual = command("docker", "network", "inspect", network_id, "--format", '{{.Id}} {{index .Labels "oan.native-worker-save.owner"}}')
            assert actual == network_id + " " + suffix, "Owned network identity mismatch"
            command("docker", "network", "rm", network_id)
        report["cleanup_complete"] = not failures
        report["verification_complete"] &= not failures
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if failures:
            raise RuntimeError("Exact owned container cleanup failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", nargs=2, metavar=("HOST", "MODE"))
    args = parser.parse_args()
    if args.probe:
        probe(*args.probe)
    else:
        run()
