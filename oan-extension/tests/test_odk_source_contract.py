"""Pure source-shaped ATI mapper regressions; no platform/database initialization."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1]/"src/openg2p_registry_oan_extension/odk/transform.py"
SPEC = importlib.util.spec_from_file_location("source_mapper", PATH)
mapper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mapper)

def source():
    return {"basic_info":{"personal_info":{"first_name_english":"Fixture","father_name_english":"Head","grandfather_name_english":"Person","gender":"male","farming_type":"mixed_farming","email":"fixture@example.invalid"}},
        "household_questions":{"household_head":"yes"},
        "land_info":{"land_info_repeat":[{"land_id":"P1","oan_land_id":"owned-land"}]},
        "crop_information":{"crop_repeat":[{"crop_name":"food_barley","crop_season":"SEASON_BELG"}],"crop_water_source":"rainfall irrigation_ground"},
        "livestock_info":{"livestock_repeat":[{"animal":"cattle","num_animals":2}],"livestock_water_source":"well_water surface_water"},
        "agricultural_input":{"fertilizer_utilized":"yes","pesticide_utilized":"no"},
        "access_to_resource":{"machinery_access":"yes","type_of_machinery":"tractor combine_harvester planter harvester combiner multi_crop_trasher maize_sheller rice_polisher"},
        "access_to_finance":{"finance_access":"yes","finance":"loan insurance saving digital_banking"}}

class SourceMapperTests(unittest.TestCase):
    def test_root_sibling_groups_keep_every_finance_machine_and_water_answer(self):
        result=mapper.intake_sections(source())
        row=result["oan_intake_fr_farmer_farm_input"][0]
        self.assertEqual(row["finance_access_types"],["LOAN","INSURANCE","SAVING","DIGITAL_BANKING"])
        self.assertNotIn("finance_access_type",row)
        self.assertTrue(row["access_to_finance"])
        self.assertEqual(row["machinery_types"],["MACH_TRACTOR","MACH_COMBINE","MACH_PLANTER","MACH_HARVESTER","MACH_COMBINER","MACH_MULTI_CROP_TRASHER","MACH_MAIZE_SHELLER","MACH_RICE_POLISHER"])
        self.assertEqual(row["water_sources"],["WS_RAINFED","WS_IRRIGATION_GROUND"])
        self.assertEqual(row["livestock_water_sources"],["WS_WELL_GROUND","WS_SURFACE_WATER"])
        self.assertTrue(row["fertilizer_use"])
        self.assertFalse(row["pesticide_use"])
        self.assertEqual(row["link_internal_record_id"],"owned-land")
        self.assertEqual(result["oan_intake_fr_farmer_crops"][0]["commodity"],"CROP_FOOD_BARLEY")

    def test_machinery_unknowns_do_not_collapse_and_crop_codes_stay_distinct(self):
        self.assertEqual(mapper.codes("standaloneharvester maize_sheller multi_crop_trasher",mapper.MACHINERY),["STANDALONEHARVESTER","MACH_MAIZE_SHELLER","MACH_MULTI_CROP_TRASHER"])
        self.assertEqual([mapper.code(x,mapper.CROPS,"CROP_") for x in ["food_barley","tea","cumin"]],["CROP_FOOD_BARLEY","CROP_TEA","CROP_CUMIN"])

    def test_multiple_lands_are_not_silently_attached_to_first(self):
        value=source();value["land_info"]["land_info_repeat"].append({"land_id":"P2","oan_land_id":"second"})
        with self.assertRaisesRegex(ValueError,"select exactly one land"):
            mapper.intake_sections(value)

    def test_actual_member_reference_and_nested_certificate_are_retained(self):
        value=source();value["other_farmers_in_hh"]={"other_farmers_in_hh_section":{"additional_farmers":"yes"},"other_farmers_repeat":[{
            "hh_member_basic_info":{"hh_member_personal_info":{"hh_member_first_name_english":"Other","hh_member_father_name_english":"Fixture","hh_member_grandfather_name_english":"Person","hh_member_gender":"female","hh_member_relationship":"Wife"}},
            "hh_member_reference_id_section":{"hh_memeber_farmer_reference_id":"ODK-MEMBER"},
            "hh_member_land_info":{"hh_member_land_info_repeat":[{"hh_member_land_certificate":"stored-certificate"}]}}]}
        result=mapper.intake_sections(value)
        self.assertTrue(result["oan_hh_information"][0]["other_farmer_in_household"])
        self.assertEqual(result["hh_members"][1]["odk_member_id"],"ODK-MEMBER")
        self.assertEqual(result["hh_members"][1]["certificate_storage_id"],"stored-certificate")
        # This is a member summary, not another Farmer submission.
        self.assertEqual(len(result["oan_fr_farmer_identity"]),1)

    def test_explicit_other_membership_names_and_farmer_fields(self):
        value=source();value["membership"]={"name_of_primary_cooperative":"other","other_primary_cooperative":"Source cooperative","name_of_union":"other","other_coop_union":"Source union"}
        result=mapper.intake_sections(value)
        row=result["oan_fr_farmer_membership"][0]
        self.assertEqual(row["primary_cooperative_name"],"Source cooperative")
        self.assertEqual(row["cooperative_union_name"],"Source union")
        row=result["oan_fr_farmer_personal_details"][0]
        self.assertEqual(row["farming_type"],"MIXED")
        self.assertEqual(row["emails"],[{"address":"fixture@example.invalid","is_primary":True}])

    def test_mapping_does_not_mutate_source(self):
        from copy import deepcopy
        value=source();value["land_info"]["land_info_repeat"][0]["crop_information"]={"crop_repeat":[{"crop_name":"tea"}]}
        before=deepcopy(value)
        mapper.intake_sections(value)
        self.assertEqual(value,before)
