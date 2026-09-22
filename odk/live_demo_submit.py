#!/usr/bin/env python3
"""
Interactive Live Demo Script for ODK Farmer Registry Ingestion.
Runs a realistic, live ODK survey submission to OpenG2P Staff API
and outputs the direct Staff Portal URL to view the created farmer.
"""

import json
import random
import sys
import time
import urllib.request
import webbrowser

DEMO_PROFILES = [
    {
        "first_en": "Desta", "father_en": "Mekonnen", "grand_en": "Tucho",
        "first_am": "ደስታ", "father_am": "መኮንን", "grand_am": "ቱቾ",
        "gender": "male", "dob_gc": "1983-07-14", "dob_ec": "1975-11-06", "age": 43,
        "crop": "WHEAT", "livestock": "CATTLE", "count": 4, "land_area": 2.75
    },
    {
        "first_en": "Genet", "father_en": "Assefa", "grand_en": "Ayele",
        "first_am": "ገነት", "father_am": "አሰፋ", "grand_am": "አየለ",
        "gender": "female", "dob_gc": "1987-12-05", "dob_ec": "1980-03-27", "age": 39,
        "crop": "TEFF", "livestock": "SHEEP", "count": 7, "land_area": 3.20
    },
    {
        "first_en": "Berhanu", "father_en": "Tamiru", "grand_en": "Bekele",
        "first_am": "ብርሃኑ", "father_am": "ታምሩ", "grand_am": "በቀለ",
        "gender": "male", "dob_gc": "1980-04-22", "dob_ec": "1972-08-14", "age": 46,
        "crop": "MAIZE", "livestock": "GOAT", "count": 6, "land_area": 4.50
    },
    {
        "first_en": "Tirhas", "father_en": "Gebre", "grand_en": "Medhin",
        "first_am": "ትርሃስ", "father_am": "ገብረ", "grand_am": "መድህን",
        "gender": "female", "dob_gc": "1991-09-18", "dob_ec": "1984-01-08", "age": 35,
        "crop": "BARLEY", "livestock": "POULTRY", "count": 25, "land_area": 1.80
    }
]

def main():
    print("=" * 65)
    print("   OpenG2P Gen 2 Farmer Registry — Live ODK Intake Demo")
    print("=" * 65)
    
    choice = input("\nUse preset realistic Ethiopian farmer profile? [Y/n]: ").strip().lower()
    if choice in ("", "y", "yes"):
        p = random.choice(DEMO_PROFILES)
        random_suffix = random.randint(1000, 9999)
        first_en = p["first_en"]
        father_en = p["father_en"]
        grand_en = p["grand_en"]
        first_am = p["first_am"]
        father_am = p["father_am"]
        grand_am = p["grand_am"]
        gender = p["gender"]
        dob_gc = p["dob_gc"]
        dob_ec = p["dob_ec"]
        age = p["age"]
        crop = p["crop"]
        livestock = p["livestock"]
        livestock_count = p["count"]
        land_area = p["land_area"]
        phone_pri = f"0911{random_suffix:04d}"
        phone_sec = f"0922{random_suffix:04d}"
        fayda_uid = f"ET-FAN-{random_suffix:06d}"
        fayda_rid = f"ET-RID-{random_suffix:06d}"
        voter_id = f"ET-VOTER-{random_suffix:05d}"
    else:
        first_en = input("First Name (English): ").strip() or "Abebe"
        father_en = input("Father Name (English): ").strip() or "Kebede"
        grand_en = input("Grandfather Name (English): ").strip() or "Bikila"
        first_am = input("First Name (Amharic): ").strip() or "አበበ"
        father_am = input("Father Name (Amharic): ").strip() or "ከበደ"
        grand_am = input("Grandfather Name (Amharic): ").strip() or "ቢቂላ"
        gender = "male"
        dob_gc = "1985-05-10"
        dob_ec = "1977-09-02"
        age = 41
        crop = input("Crop Commodity (e.g., WHEAT, TEFF, MAIZE): ").strip().upper() or "WHEAT"
        livestock = input("Livestock Type (e.g., CATTLE, SHEEP, GOAT): ").strip().upper() or "CATTLE"
        livestock_count = 5
        land_area = 3.5
        phone_pri = f"0911{random.randint(1000, 9999):04d}"
        phone_sec = f"0922{random.randint(1000, 9999):04d}"
        fayda_uid = f"ET-FAN-{random.randint(100000, 999999)}"
        fayda_rid = f"ET-RID-{random.randint(100000, 999999)}"
        voter_id = f"ET-VOTER-{random.randint(10000, 99999)}"

    payload = {
        "data": {
            "basic_info": {
                "personal_info": {
                    "first_name_english": first_en,
                    "father_name_english": father_en,
                    "grandfather_name_english": grand_en,
                    "first_name_amharic": first_am,
                    "father_name_amharic": father_am,
                    "grandfather_name_amharic": grand_am,
                    "first_name_other": first_en,
                    "father_name_other": father_en,
                    "grandfather_name_other": grand_en,
                    "gender": gender,
                    "date_of_birth": dob_gc,
                    "date_of_birth_ec": dob_ec,
                    "age": age,
                    "has_personal_phone": "yes",
                    "primary_phone_number": phone_pri,
                    "secondary_phone_number": phone_sec,
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
                "education_level": "secondary"
            },
            "national_id_section": {
                "national_fan": fayda_uid,
                "national_rid": fayda_rid,
                "other_id": voter_id
            },
            "farmer_reference_id": {
                "farmer_reference_id": f"ET-REF-LIVE-{int(time.time())}"
            },
            "land_info": {
                "land_info_repeat": [
                    {
                        "land_ownership": "OWNED",
                        "total_land_area": land_area,
                        "land_id": f"LND-{random.randint(100, 999)}",
                        "land_kebele": "Babogaya"
                    }
                ]
            },
            "crop_information": {
                "crop_repeat": [
                    {
                        "crop_name_rep": crop,
                        "crop_date": "2026-06-15"
                    }
                ]
            },
            "livestock_info": {
                "livestock_repeat": [
                    {
                        "animal_rep": livestock,
                        "num_animals": livestock_count
                    }
                ]
            },
            "other_hh_members": {
                "other_hh_members_repeat": [
                    {
                        "other_member_name_english": f"Spouse of {first_en}",
                        "household_relationship": "SPOUSE",
                        "member_gender": "female",
                        "member_dob": "1988-06-20"
                    }
                ]
            },
            "farmer_location": {
                "location": f"{8.7850 + random.uniform(-0.01, 0.01):.7f} {38.9100 + random.uniform(-0.01, 0.01):.7f} 1890.00 2.20"
            },
            "survey_metadata": {
                "enumerator_name": "Field Officer Demo",
                "enumerator_id": "demo_agent_live",
                "survey_start": "2026-09-11"
            }
        }
    }

    print("\n[+] Submitting ODK survey to OpenG2P webhook...")
    req = urllib.request.Request(
        "http://localhost:8001/api/v1/farmer-registry/odk/test-submission",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            print("[+] Ingestion Response:")
            print(json.dumps(res_data, indent=2, ensure_ascii=False))

            int_id = res_data.get("internal_record_id")
            func_id = res_data.get("functional_record_id")
            url = f"http://localhost:3001/en/register/farmer/{int_id}"

            print("\n" + "=" * 65)
            print(f"SUCCESS! Farmer Profile Created:")
            print(f"  - Functional ID:  {func_id}")
            print(f"  - Internal ID:    {int_id}")
            print(f"  - Name:           {first_en} {father_en} ({first_am} {father_am})")
            print(f"  - Direct URL:     {url}")
            print("=" * 65)

            open_browser = input("\nOpen profile in Staff Portal browser now? [Y/n]: ").strip().lower()
            if open_browser in ("", "y", "yes"):
                webbrowser.open(url)
    except Exception as e:
        print(f"[-] Submission failed: {e}")

if __name__ == "__main__":
    main()
