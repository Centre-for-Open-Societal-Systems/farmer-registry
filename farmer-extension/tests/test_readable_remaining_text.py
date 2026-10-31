"""The third readable-text seed (87_readable_remaining_text.sql): the keys it
names carry plain English, and no stale wording survives in the same file."""
import json
import re
from pathlib import Path

_SEED = (Path(__file__).resolve().parents[1]
         / "src/openg2p_registry_farmer_extension/meta_data/zz-oan/87_readable_remaining_text.sql")
_TEXT = _SEED.read_text(encoding="utf-8")


def _blocks():
    pattern = re.compile(r"'([{]\n.*?\n[}])'::jsonb", re.S)
    return [json.loads(block) for block in pattern.findall(_TEXT)]


def _domain():
    return _blocks()[1]


def test_platform_upload_words_are_flat_dotted_keys():
    assert _blocks()[0] == {"common.remove": "Remove", "common.select": "Select"}


def test_every_document_slot_has_a_label():
    domain = _domain()
    for kind in ("identity", "bank", "land", "representative", "farmer", "other"):
        for number in range(1, 6):
            label = domain[f"{kind}_document_{number}"]
            assert label == f"{kind.capitalize()} document {number}"
            assert "_" not in label


def test_one_fayda_name_for_the_fan_or_fin():
    domain = _domain()
    for key in ("fayda_fin", "foundational_id", "FAYDA"):
        assert domain[key] == "Fayda ID (FAN or FIN)"
    assert "credential" not in _TEXT.lower().replace("-- ", "")


def test_unclear_labels_are_replaced():
    domain = _domain()
    assert domain["disabled"] == "Has a disability"
    assert domain["size_of_group"] == "Household size"
    assert domain["is_primary"] == "Primary phone number"
    assert domain["location_hierarchy"] == "Administrative hierarchy"
    assert domain["plus_code"] == "Plus code (map location)"
    assert domain["computation_scores"] == domain["household_computation_scores"] == "Poverty score"


def test_task_and_history_words_are_sentence_case():
    domain = _domain()
    for key, text in {"approver": "Approval", "skipped": "Skipped", "request_created": "Request created",
                      "stage_completed": "Stage completed"}.items():
        assert domain[key] == text


_LABELS = (Path(__file__).resolve().parents[1]
           / "src/openg2p_registry_farmer_extension/meta_data/zz-oan/87_readable_text_labels.sql").read_text(encoding="utf-8")


def test_the_fourth_pass_labels_say_what_the_field_holds():
    block = json.loads(re.search(r"'([{]\n.*?\n[}])'::jsonb", _LABELS, re.S).group(1))
    assert block["other_land_owner"] == "Another land owner in the household"
    assert block["enumerator_accuracy"] == "Enumerator GPS accuracy (metres)"
    assert block["farmer_document"] == "Farmer or cooperative membership document"
    assert block["total_land_crop_sharing_area"] == "Crop-sharing or other land (ha)"
    assert block["Intake Form"] == "Intake form"
    assert "Household scores" in _LABELS


def test_code_texts_match_the_pack():
    block = json.loads(re.search(r"'([{]\n.*?\n[}])'::jsonb", _LABELS, re.S).group(1))
    assert block["BASIC"] == "Basic education"
    assert block["INTERMEDIARY"] == "Intermediate (middle school)"
    assert block["CROP_SHARE"] == "Sharecropper"
    assert block["SELF"] == "Head of household"
