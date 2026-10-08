#!/usr/bin/env python3
"""
Test script for verifying odk/templates/farmer_transform.j2 locally.
Loads sample ODK Central survey JSON, renders it with Jinja2,
and validates that the output is valid JSON matching OpenG2P intake schema.
"""

import json
import os
import sys

try:
    import jinja2
except ImportError:
    print("Error: jinja2 is required. Install it using: pip install jinja2")
    sys.exit(1)

# Sample realistic ODK Central survey payload (matches ATI_Farmers_Profile_ODK_Form_v2)
SAMPLE_ODK_PAYLOAD = {
    "expanded": {
        "basic_info": {
            "personal_info": {
                "first_name_english": "Desta",
                "father_name_english": "Mekonnen",
                "grandfather_name_english": "Tucho",
                "first_name_amharic": "ደስታ",
                "father_name_amharic": "መኮንን",
                "grandfather_name_amharic": "ቱቾ",
                "first_name_other": "Desta",
                "father_name_other": "Mekonnen",
                "grandfather_name_other": "Tucho",
                "gender": "male",
                "date_of_birth": "1983-07-14",
                "date_of_birth_ec": "1975-11-06",
                "age": 43,
                "has_personal_phone": "yes",
                "primary_phone_number": "251911234567",
                "secondary_phone_number": "251922345678",
                "other_phone_number": "+251933445566",
                "farming_type": "MIXED",
                "disability": "no"
            },
            # The form stores codes, without their leading zero (Oromia / Arsi /
            # Merti / Abomsa_01 in KebeleList.csv).
            "locale_info": {
                "region": "4",
                "zone": "408",
                "woreda": "40801",
                "kebele": "40801101001",
                "language": "Amharic",
                "local_language": "Afaan Oromo"
            }
        },
        "household_questions": {
            "household_head": "yes",
            "is_psnp_user": "no"
        },
        "socio_economic_data": {
            "marital_status": "married",
            "education_level": "secondary",
            "income_source": "CROP_PRODUCTION"
        },
        "national_id_section": {
            "national_id": "yes",
            "national_uid": "1234 5678 9012 3456",
            "national_rid": "10001100010000120230510123456"
        },
        "farmer_reference_id": {
            "farmer_reference_id": "ET-REF-LIVE-999"
        },
        # Its own ODK group, like the farmer photo section on the intake form.
        "farmer_photo_section": {
            "farmer_photo": {"__type": "File", "name": "desta_profile.jpg",
                             "type": "image/jpeg", "data": "/9j/4AAQ"}
        },
        "land_info": {
            "land_info_repeat": [
                {
                    "land_ownership": "tenant",
                    # The connector inlines the photo (embed_attachments).
                    "land_certificate": {"__type": "File", "name": "deed.jpg",
                                         "type": "image/jpeg", "data": "/9j/4AAQ"},
                    "total_land_area": 2.75,
                    "land_id": "LND-001",
                    "land_kebele": "Babogaya"
                }
            ]
        },
        "crop_information": {
            "crop_repeat": [
                {
                    "crop_name_rep": "WHEAT",
                    "crop_date": "2026-06-15"
                }
            ]
        },
        "livestock_info": {
            "livestock_repeat": [
                {
                    "animal_rep": "CATTLE",
                    "num_animals": 4
                }
            ]
        },
        "agricultural_input": {
            "fertilizer_use": "yes",
            "fertilizer_amount": 50.0,
            "pesticide_use": "no"
        },
        "membership": {
            "primary_cooperative": "yes",
            "name_of_primary_cooperative": "Adaa Farmers Primary Coop",
            "coop_union": "yes",
            "name_of_coop_union": "Lume Adama Union",
            "farmer_cluster": "yes",
            "farmer_role": "LEAD",
            "primary_commodity": "WHEAT"
        },
        "other_hh_members": {
            "other_hh_members_repeat": [
                {
                    "other_member_name_english": "Genet Assefa Ayele",
                    "household_relationship": "SPOUSE",
                    "member_gender": "female",
                    "member_dob": "1987-12-05"
                }
            ]
        },
        "farmer_location": {
            # OData returns a geopoint as GeoJSON: [lon, lat, alt].
            "location": {"type": "Point", "coordinates": [38.91, 8.785, 1890.0],
                         "properties": {"accuracy": 2.2}}
        },
        "survey_metadata": {
            "enumerator_name": "Field Officer Demo",
            "enumerator_id": "demo_agent_live",
            "survey_start": "2026-09-17"
        }
    }
}

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, "templates", "farmer_transform.j2")

    print(f"[1] Loading template: {template_path}")
    if not os.path.exists(template_path):
        print(f"[-] Template not found at {template_path}")
        sys.exit(1)

    with open(template_path, "r", encoding="utf-8") as f:
        template_str = f.read()

    print("[2] Compiling Jinja2 template...")
    env = jinja2.Environment()
    template = env.from_string(template_str)

    print("[3] Rendering template with sample ODK survey payload...")
    rendered_output = template.render(**SAMPLE_ODK_PAYLOAD)

    print("[4] Validating that rendered output is valid JSON...")
    try:
        parsed_json = json.loads(rendered_output)
    except json.JSONDecodeError as e:
        print(f"[-] FAILED: Rendered output is not valid JSON! Error: {e}")
        print("\n--- Rendered Output ---")
        print(rendered_output)
        sys.exit(1)

    location = parsed_json["fr_farmer_location"][0]
    land = parsed_json["intake_fr_farmer_land"][0]
    expectations = [
        ("location id", location.get("geo_lowest_level_value_id"), "kebele-ET040801101001"),
        ("latitude", location.get("latitude"), "8.785"),
        ("longitude", location.get("longitude"), "38.91"),
        ("land ownership", land.get("land_ownership_type"), "TENANT"),
        ("land certificate", (land.get("certificate_storage_id") or {}).get("name"), "deed.jpg"),
        ("certificate provided", land.get("certificate_provided"), True),
        ("farmer photo", ((parsed_json.get("fr_farmer_photo") or [{}])[0]
                          .get("record_image_document_id") or {}).get("name"), "desta_profile.jpg"),
        # The form only takes 251XXXXXXXXX; the registry gets the 9-digit national number.
        ("primary phone", parsed_json["fr_farmer_phone_numbers"][0].get("phone_number"), "911234567"),
    ]
    wrong = [f"{name}: {got!r}, expected {want!r}" for name, got, want in expectations if got != want]
    if wrong:
        print("[-] FAILED: " + "; ".join(wrong))
        sys.exit(1)

    # A bare file name (image not downloaded) must not produce a photo section.
    bare = json.loads(template.render(expanded={
        **SAMPLE_ODK_PAYLOAD["expanded"],
        "farmer_photo_section": {"farmer_photo": "desta_profile.jpg"}}))
    if "fr_farmer_photo" in bare:
        print("[-] FAILED: bare photo file name produced an fr_farmer_photo section")
        sys.exit(1)

    # Household members collected as full farmers carry their own land
    # certificate, nested in their land repeat.
    base = {k: v for k, v in SAMPLE_ODK_PAYLOAD["expanded"].items() if k != "other_hh_members"}
    cert = {"__type": "File", "name": "member_deed.jpg", "type": "image/jpeg", "data": "/9j/4AAQ"}
    member = lambda first, land_cert: {
        "hh_member_basic_info": {"hh_member_personal_info": {
            "hh_member_first_name_english": first, "hh_member_father_name_english": "Tadesse",
            "hh_member_grandfather_name_english": "Bekele", "hh_member_gender": "male",
            "hh_member_date_of_birth": "1990-01-02"}},
        "hh_member_land_info": {"hh_member_land_info_repeat": [{"hh_member_land_certificate": land_cert}]},
    }
    with_members = json.loads(template.render(expanded={**base, "other_farmers_in_hh": {
        "other_farmers_repeat": [member("Abel", cert), member("Birtukan", "bare_name.jpg")]}}))
    abel, birtukan = with_members["fr_household_members"]
    member_checks = [
        ("member name", abel.get("first_name"), "Abel"),
        ("member birth date", abel.get("birth_date"), "1990-01-02"),
        ("member certificate", (abel.get("certificate_storage_id") or {}).get("name"), "member_deed.jpg"),
        ("member certificate provided", abel.get("certificate_provided"), True),
        ("member bare file name left out", "certificate_storage_id" in birtukan, False),
    ]
    wrong = [f"{n}: {g!r}, expected {w!r}" for n, g, w in member_checks if g != w]
    if wrong:
        print("[-] FAILED: " + "; ".join(wrong))
        sys.exit(1)

    seasons = {"MEHER", "BELG", "IRRIGATED", "PERENNIAL"}
    bad = [c.get("season") for c in parsed_json.get("intake_fr_farmer_crops", [])
           if c.get("season") not in seasons]
    if bad:
        print(f"[-] FAILED: crop season(s) {bad} are not among {sorted(seasons)}")
        sys.exit(1)

    print("[+] SUCCESS! Valid JSON produced.\n")
    print("=" * 60)
    print("Generated Intake Sections Summary:")
    print("=" * 60)
    for section_key, section_data in parsed_json.items():
        count = len(section_data) if isinstance(section_data, list) else 1
        print(f" • {section_key:<50} ({count} record{'s' if count != 1 else ''})")

    print("\n" + "=" * 60)
    print("Detailed Intake JSON Preview:")
    print("=" * 60)
    print(json.dumps(parsed_json, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
