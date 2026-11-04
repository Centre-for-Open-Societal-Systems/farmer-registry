"""The farmer_reference block: every Farmer-tab field Crop Sown and Livestock keep, and the photo.

Renders the DCI search response and the change notice the way the registry
renders them (ChainableUndefined, sorted JSON), without the platform installed.
"""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

from jinja2 import ChainableUndefined, Environment, Undefined

ROOT = Path(__file__).resolve().parents[2]
EXTENSION = ROOT / "farmer-extension/src/openg2p_registry_farmer_extension"
TEMPLATES = EXTENSION / "templates"
CATALOGUE = EXTENSION / "meta_data/data-scopes/farmer_reference.json"

JPEG = b"\xff\xd8\xff\xe0" + b"photo-bytes" * 10


def _load_photo_module():
    spec = importlib.util.spec_from_file_location(
        "dci_photo", EXTENSION / "register_domain/services/dci_photo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dci_photo = _load_photo_module()


def _default(value):
    if isinstance(value, Undefined):
        return None
    raise TypeError(type(value).__name__)


def _env(with_photo=True, stored=None):
    env = Environment(undefined=ChainableUndefined)
    env.policies["json.dumps_kwargs"] = {"sort_keys": True, "default": _default}
    if with_photo:
        objects = stored if stored is not None else {("documents", "abc123"): JPEG}
        env.globals["farmer_photo"] = dci_photo.make_photo_function(
            lambda name, bucket: objects[(bucket, name)])
    return env


FARMER = {
    "internal_record_id": "i-1", "functional_record_id": "FR-000000000123", "foundational_id": "1234 5678 9012 3456",
    "last_approved_at": "2026-11-01T10:00:00", "record_status": "ACTIVE",
    "record_image_document_id": "doc-1",
    "record_image_url": "https://minio-farmer.example.org/documents/abc123?X-Amz-Signature=x",
    "has_national_id": True, "rid": "12345678901234567890123456789", "odk_farmer_id": "ODK-1", "pula_id": "P-1",
    "first_name": "Abebe", "middle_name": "Kebede", "last_name": "Bekele",
    "language_spoken": "OROMO", "first_name_local": "Abbee", "middle_name_local": "Kabbadaa", "last_name_local": "Baqqalaa",
    "gender": "MALE", "birth_date": "1980-01-01", "birth_date_ec": "1972-04-22", "estimated_age": 46,
    "marital_status": "MARRIED", "education_level": "BASIC",
    "disabled": True, "disability_type": "VISUAL", "disability_severity": "MILD",
    "source_of_income": "SOI_OTHERS", "source_of_income_other": "Trading",
    "income_sources": ["SOI_CROP", "SOI_LIVESTOCK", "SOI_OTHERS"],
    "is_psnp_user": False, "is_farmer": True, "farming_type": "MIXED",
    "email": "abebe@example.org",
    "address_line_1": "Kebele 01", "address_line_2": None, "postal_code": "1000", "country_code": "ET",
    "plus_code": "6FR5+2X", "latitude": 9.1, "longitude": 38.7, "altitude": 2350.0,
    "geo_lowest_level_value_id": "k-1",
    "geo_code_hierarchy_json": {"hierarchy": [
        {"level_mnemonic": "region", "level_value_id": "r-1", "level_value_mnemonic": "Oromia"},
        {"level_mnemonic": "woreda", "level_value_id": "w-1", "level_value_mnemonic": "Ada'a"}]},
    "farmer_phone": [
        {"phone_type": "SECONDARY", "phone_number": "922222222", "country_code": "+251", "is_primary": False,
         "phone_e164": "+251922222222", "last_approved_at": "2026-11-02T08:30:00"},
        {"phone_type": "PRIMARY", "phone_number": "911111111", "country_code": "+251", "is_primary": True,
         "phone_e164": "+251911111111", "last_approved_at": "2026-10-01T08:30:00"},
    ],
}


def _block(record, **env_options):
    template = _env(**env_options).from_string(
        (TEMPLATES / "farmer_dci_search_response.j2").read_text(encoding="utf-8"))
    return json.loads(template.render(expanded=record))["farmer_reference"]


def test_block_carries_every_farmer_tab_field():
    block = _block(FARMER)
    for key in ("has_national_id", "rid", "odk_farmer_id", "pula_id", "language_spoken", "birth_date_ec",
                "estimated_age", "marital_status", "education_level", "disabled", "disability_type",
                "disability_severity", "source_of_income", "source_of_income_other", "income_sources", "is_psnp_user", "is_farmer",
                "farming_type", "email", "plus_code", "latitude", "longitude", "altitude"):
        assert block[key] == FARMER[key], key
    assert block["fan"] == "1234567890123456" and block["fin"] is None
    assert block["region_name"] == "Oromia" and block["woreda_id"] == "w-1"


def test_local_names_go_to_other_unless_the_language_is_amharic():
    block = _block(FARMER)
    assert (block["first_name_other"], block["last_name_other"]) == ("Abbee", "Baqqalaa")
    assert block["first_name_amh"] is None
    amharic = _block({**FARMER, "language_spoken": "AMHARIC"})
    assert amharic["first_name_amh"] == "Abbee" and amharic["first_name_other"] is None


def test_all_phones_with_the_primary_as_mobile_number():
    block = _block(FARMER)
    assert [p["phone_number"] for p in block["phones"]] == ["922222222", "911111111"]
    assert block["phones"][1] == {"phone_type": "PRIMARY", "phone_number": "911111111", "country_code": "+251",
                                  "is_primary": True, "phone_e164": "+251911111111"}
    assert block["mobile_number"] == "911111111"


def test_approved_at_is_the_latest_approval_of_the_farmer_or_a_phone():
    assert _block(FARMER)["approved_at"] == "2026-11-02T08:30:00Z"
    no_phones = _block({**FARMER, "farmer_phone": []})
    assert no_phones["approved_at"] == "2026-11-01T10:00:00Z" and no_phones["phones"] == []


def test_photo_travels_as_bytes_with_its_hash():
    photo = _block(FARMER)["photo"]
    assert photo == {"content_type": "image/jpeg", "sha256": hashlib.sha256(JPEG).hexdigest(),
                     "data": base64.b64encode(JPEG).decode("ascii")}


def test_no_photo_without_url_function_or_readable_image():
    assert _block({**FARMER, "record_image_url": None})["photo"] is None
    assert _block(FARMER, with_photo=False)["photo"] is None
    assert _block(FARMER, stored={})["photo"] is None
    assert _block(FARMER, stored={("documents", "abc123"): b"not an image"})["photo"] is None
    other_bucket = {**FARMER, "record_image_url": "https://minio/templates/abc123"}
    assert _block(other_bucket)["photo"] is None


class _Page:
    def __init__(self, records):
        self.records = records


def test_search_records_get_the_image_url_of_their_photo_document():
    # The partner search returns table columns only: the document id, no URL.
    searched = {key: value for key, value in FARMER.items() if key != "record_image_url"}
    no_photo = {"internal_record_id": "i-2", "record_image_document_id": None}
    has_url = {"internal_record_id": "i-3", "record_image_document_id": "doc-3", "record_image_url": "https://x/documents/k"}
    unknown = {"internal_record_id": "i-4", "record_image_document_id": "doc-gone"}
    records = dci_photo.records_missing_image_url([_Page([searched, no_photo, has_url]), _Page([unknown])])
    assert [record["internal_record_id"] for record in records] == ["i-1", "i-4"]
    dci_photo.add_record_image_urls(records, {"doc-1": FARMER["record_image_url"]})
    assert searched["record_image_url"] == FARMER["record_image_url"]
    assert "record_image_url" not in unknown
    assert _block(searched)["photo"]["sha256"] == hashlib.sha256(JPEG).hexdigest()


def test_oversized_photo_is_left_out():
    big = b"\xff\xd8\xff" + b"0" * dci_photo.MAX_PHOTO_BYTES
    assert dci_photo.encode_photo(big) is None


def test_block_leaves_out_verification_documents_and_staff():
    block = _block({**FARMER, "last_authentication_status": "SUCCESS", "created_by": "staff-1",
                    "last_approved_by": "staff-2", "documents": [{"label": "identity_1"}]})
    assert not {"last_authentication_status", "created_by", "last_approved_by", "documents"} & set(block)


def test_notice_event_changes_with_a_phone_only_approval():
    template = _env().from_string((TEMPLATES / "farmer_reference_changed_v1.j2").read_text(encoding="utf-8"))
    notice = json.loads(template.render(expanded={**FARMER, "foundational_id": "1234567890123456"}))
    assert notice == {"event_id": "i-1:2026-11-02T08:30:00", "event_type": "farmer_reference.changed.v1",
                      "farmer_id": "FR-000000000123", "fayda_fan_id": "1234567890123456"}


def test_scope_releases_every_field_the_block_reads():
    scope = json.loads(CATALOGUE.read_text(encoding="utf-8"))["scopes"][0]
    assert scope["name"] == "farmer_reference"
    fields = set(scope["fields"])
    template = (TEMPLATES / "farmer_dci_search_response.j2").read_text(encoding="utf-8")
    block = template[template.index('"farmer_reference": {'):]
    import re
    read = set(re.findall(r"source\.get\('([a-z0-9_]+)'\)", template[template.index("{#- The Farmer reference"):]))
    read -= {"farmer_phone"}
    assert {f"Farmer.{name}" for name in read} <= fields
    phone_read = set(re.findall(r"item\.get\('([a-z0-9_]+)'\)", block))
    assert {f"FarmerPhone.{name}" for name in phone_read} <= fields
    assert not any("authentication" in f or "documents" in f or f.endswith("_by") for f in fields)
