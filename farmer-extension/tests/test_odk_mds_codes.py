"""A submission of the Master Data driven form (odk/tools/build_mds_form.py)
reaches the intake with its codes unchanged: the form's choice names are the
list codes, so no alias table sits between the form and the registry."""
from openg2p_registry_farmer_extension.odk.transform import SECTIONS, intake_sections

SUBMISSION = {
    "meta": {"instanceID": "uuid:mds-form"},
    "household_questions": {"household_head": "yes", "head_registered": "no"},
    "national_id_section": {"national_id": "yes", "national_uid": "412345678905",
                            "identity_document_type": "KEBELE_WOREDA_ID", "identity_document": "doc-1"},
    "basic_info": {
        "locale_info": {"region": "ET04", "region_code": "ET04", "region_name": "Oromia",
                        "zone": "ET0408", "zone_code": "ET0408", "zone_name": "West Shewa",
                        "woreda": "ET040801", "woreda_code": "ET040801", "woreda_name": "Ambo",
                        "kebele": "ET04080101", "kebele_code": "ET04080101", "kebele_name": "Kebele 01",
                        "language": "AFAAN_OROMO"},
        "personal_info": {"first_name_english": "Chaltu", "father_name_english": "Bekele", "grandfather_name_english": "Tola",
                          "gender": "FEMALE", "date_of_birth": "1990-01-01", "age": 36, "phone_number": "yes",
                          "primary_phone_number": "0911000000", "farming_type": "MIXED", "disability": "no"}},
    "socio_economic_data": {"marital_status": "MARRIED", "education_level": "CAN_READ_AND_WRITE",
                            "income_source": "SOI_CROP_PRODUCTION SOI_LIVESTOCK_PRODUCTION"},
    "membership": {"primary_cooperative": "no", "coop_union": "no", "farmer_cluster": "yes",
                   "primary_commodity": "CROP_TEFF", "farmer_role": "LEAD"},
    "land_info": {"land_info_repeat": [{"land_ownership": "OWNER", "total_land_area": "1.5", "land_id": "LAND-1", "oan_land_id": "land-uuid-1"}]},
    "crop_information": {"crop_water_source": "WS_RAINFED WS_IRRIGATION_SURFACE",
                         "crop_repeat": [{"crop_land_id": "LAND-1", "crop_name": "CROP_BREAD_WHEAT", "crop_date": "2026-07-01", "crop_season": "SEASON_MEHER"}]},
    "livestock_info": {"livestock_water_source": "WS_SURFACE_WATER",
                       "livestock_repeat": [{"livestock_land_id": "LAND-1", "animal": "LSTK_GOAT", "num_animals": "3"}]},
    "farm_input_land_id": "LAND-1",
    "agricultural_input": {"fertilizer_utilized": "yes", "pesticide_utilized": "no", "insecticide_utilized": "no", "improved_seed_utilized": "no"},
    "access_to_resource": {"machinery_access": "yes", "type_of_machinery": "MACH_TRACTOR MACH_SPRAYER"},
    "access_to_finance": {"finance_access": "yes", "finance": "LOAN SAVING"},
    "other_hh_members": {"other_hh_members_yes_no": "yes", "other_hh_members_repeat": [
        {"other_member_name_english": "Abebe Bekele Tola", "member_gender": "MALE", "member_dob": "2010-01-01",
         "household_relationship": "CHILD"}]},
    "farmer_location": {"location": "8.98 37.85 2100 5"},
}


def test_master_data_codes_pass_through_unchanged():
    out = intake_sections(SUBMISSION)
    assert out[SECTIONS[2]][0]["language_spoken"] == "AFAAN_OROMO"
    assert out[SECTIONS[3]][0]["gender"] == "FEMALE"
    assert out[SECTIONS[3]][0]["marital_status"] == "MARRIED"
    assert out[SECTIONS[3]][0]["farming_type"] == "MIXED"
    assert out[SECTIONS[6]][0]["education_level"] == "CAN_READ_AND_WRITE"
    assert out[SECTIONS[6]][0]["income_sources"] == ["SOI_CROP_PRODUCTION", "SOI_LIVESTOCK_PRODUCTION"]
    assert out[SECTIONS[10]][0]["land_ownership_type"] == "OWNER"
    crop = out[SECTIONS[11]][0]
    assert (crop["commodity"], crop["season"]) == ("CROP_BREAD_WHEAT", "SEASON_MEHER")
    inputs = out[SECTIONS[12]][0]
    # The form asks the crops' water source once, for the holding's inputs row.
    assert inputs["water_sources"] == ["WS_RAINFED", "WS_IRRIGATION_SURFACE"]
    assert inputs["machinery_types"] == ["MACH_TRACTOR", "MACH_SPRAYER"]
    assert inputs["finance_access_types"] == ["LOAN", "SAVING"]
    assert inputs["livestock_water_sources"] == ["WS_SURFACE_WATER"]
    assert out[SECTIONS[13]][0]["livestock_type"] == "LSTK_GOAT"
    assert out[SECTIONS[14]][0]["farmer_cluster_role"] == "LEAD"
    assert out[SECTIONS[14]][0]["primary_commodity"] == "CROP_TEFF"
    assert out[SECTIONS[15]][0]["identity_document_type"] == "KEBELE_WOREDA_ID"
    assert out[SECTIONS[8]][1]["relationship_to_the_head"] == "CHILD"


def test_pack_geography_codes_become_the_location_hierarchy():
    location = intake_sections(SUBMISSION)[SECTIONS[9]][0]
    assert location["geo_lowest_level_value_id"] == "ET04080101"
    hierarchy = __import__("json").loads(location["geo_code_hierarchy_json"])["hierarchy"]
    assert [(h["level_mnemonic"], h["level_value_id"]) for h in hierarchy] == [
        ("REGION", "ET04"), ("ZONE", "ET0408"), ("WOREDA", "ET040801"), ("KEBELE", "ET04080101")]
    assert location["latitude"] == 8.98 and location["longitude"] == 37.85
