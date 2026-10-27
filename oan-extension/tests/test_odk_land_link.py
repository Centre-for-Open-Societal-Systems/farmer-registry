"""Actual root-group source shape with independent native child parent links."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1]/'src/openg2p_registry_oan_extension/odk/transform.py'
SPEC = importlib.util.spec_from_file_location('land_link_mapper', PATH)
mapper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mapper)


def submission():
    return {
        'land_info': {'land_info_repeat': [
            {'land_id': 'PARCEL-A', 'oan_land_id': 'native-land-a'},
            {'land_id': 'PARCEL-B', 'oan_land_id': 'native-land-b'},
        ]},
        'crop_information': {'crop_repeat': [{'crop_name': 'maize', 'crop_land_id': 'PARCEL-B'}]},
        'livestock_info': {'livestock_repeat': [{'animal': 'cattle', 'livestock_land_id': 'PARCEL-A', 'num_animals': 2}]},
        'farm_input_land_id': 'PARCEL-B',
        'access_to_finance': {'finance_access': 'yes', 'finance': 'loan insurance'},
    }


class LandLinkTests(unittest.TestCase):
    def test_each_actual_repeat_and_root_inputs_use_the_selected_parent(self):
        value = submission()
        original = deepcopy(value)
        sections = mapper.intake_sections(value)
        self.assertEqual(sections['oan_intake_fr_farmer_crops'][0]['link_internal_record_id'], 'native-land-b')
        self.assertEqual(sections['oan_intake_fr_farmer_livestocks'][0]['link_internal_record_id'], 'native-land-a')
        inputs = sections['oan_intake_fr_farmer_farm_input'][0]
        self.assertEqual(inputs['link_internal_record_id'], 'native-land-b')
        self.assertEqual(inputs['finance_access_types'], ['LOAN', 'INSURANCE'])
        self.assertEqual(value, original)

    def test_missing_selection_is_never_guessed_with_multiple_parents(self):
        value = submission()
        del value['crop_information']['crop_repeat'][0]['crop_land_id']
        with self.assertRaisesRegex(ValueError, 'select exactly one land'):
            mapper.intake_sections(value)

    def test_removed_or_foreign_parcel_is_rejected(self):
        value = submission()
        value['farm_input_land_id'] = 'REMOVED-PARCEL'
        with self.assertRaisesRegex(ValueError, 'select exactly one land'):
            mapper.intake_sections(value)

    def test_conflicting_identifiers_cannot_redirect_a_child(self):
        value = submission()
        value['crop_information']['crop_repeat'][0]['oan_land_id'] = 'native-land-a'
        with self.assertRaisesRegex(ValueError, 'select exactly one land'):
            mapper.intake_sections(value)

    def test_duplicate_parcel_labels_are_ambiguous(self):
        lands = submission()['land_info']['land_info_repeat']
        lands[1]['land_id'] = 'PARCEL-A'
        with self.assertRaisesRegex(ValueError, 'select exactly one land'):
            mapper.child_land({'crop_land_id': 'PARCEL-A'}, lands)

    def test_legacy_id_and_native_id_can_agree_on_the_same_parent(self):
        lands = submission()['land_info']['land_info_repeat']
        self.assertEqual(mapper.child_land({'land_id': 'PARCEL-A', 'oan_land_id': 'native-land-a'}, lands), 'native-land-a')
