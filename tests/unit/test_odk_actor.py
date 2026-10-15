"""The ODK collector displayed in the form also owns ingested submissions."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Template

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


actor = load("odk_actor", "farmer-extension/src/openg2p_registry_farmer_extension/odk_actor.py")
patcher = load("patch_odk_actor", "docker/celery/assets/patch_odk_actor.py")


@pytest.mark.parametrize("data,name", [
    ({"survey_metadata": {"enumerator_name": "Field Collector"},
      "__system": {"submitterName": "Shared Device"}}, "Field Collector"),
    ({"__system": {"submitterName": "Central Submitter"}}, "Central Submitter"),
    ({"survey_metadata": {"enumerator_name": "  "},
      "__system": {"submitterName": "  አበበ Field Officer  "}}, "አበበ Field Officer"),
    ({"survey_metadata": {"enumerator_name": {"name": "invalid"}},
      "__system": {"submitterName": "Uploader"}}, "Uploader"),
    ({"survey_metadata": [], "__system": []}, "system"),
    ({}, "system"),
])
@pytest.mark.parametrize("wrapped", [False, True])
def test_form_and_audit_attribution_agree(data, name, wrapped):
    data = {**data, "basic_info": {"personal_info": {"first_name": "Synthetic"}}}
    expanded = {"payload": data} if wrapped else data
    enriched = SimpleNamespace(enriched_data_json=expanded)
    classified = SimpleNamespace(data_model_id="FARMER_ODK_MODEL")
    assert actor.ingestion_created_by(classified, enriched) == name
    result = json.loads(Template((ROOT / "odk/templates/farmer_transform.j2").read_text()).render(expanded=expanded))
    assert result["fr_farmer_enumerator"][0]["enumerator_name"] == ("" if name == "system" else name)


def test_unrelated_models_and_missing_payload_keep_platform_default():
    enriched = SimpleNamespace(enriched_data_json={"survey_metadata": {"enumerator_name": "Other Model"}})
    assert actor.ingestion_created_by(SimpleNamespace(data_model_id="OTHER"), enriched) == "system"
    for payload in [None, [], "not-json"]:
        assert actor.ingestion_created_by(SimpleNamespace(data_model_id="FARMER_ODK_MODEL"),
                                         SimpleNamespace(enriched_data_json=payload)) == "system"


@pytest.mark.parametrize("replacements", [patcher.INTAKE_REPLACEMENTS, patcher.CHANGE_REPLACEMENTS])
def test_patch_rejects_platform_drift_without_writing(tmp_path, replacements):
    path = tmp_path / "worker.py"
    original = "async def changed_platform(): pass\n"
    path.write_text(original)
    with pytest.raises(RuntimeError, match="Platform ingestion changed"):
        patcher.patch(path, replacements)
    assert path.read_text() == original
