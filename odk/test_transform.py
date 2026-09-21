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
                "primary_phone_number": "0911234567",
                "secondary_phone_number": "0922345678",
                "farming_type": "MIXED",
                "disability": "no"
            },
            "locale_info": {
                "region": "Oromia",
                "zone": "East Shewa",
                "woreda": "Adaa",
                "kebele": "Babogaya",
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
            "national_fan": "ET-FAN-987654",
            "national_rid": "ET-RID-123456"
        },
        "farmer_reference_id": {
            "farmer_reference_id": "ET-REF-LIVE-999"
        },
        "land_info": {
            "land_info_repeat": [
                {
                    "land_ownership": "OWNED",
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
            "location": "8.7850000 38.9100000 1890.00 2.20"
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
