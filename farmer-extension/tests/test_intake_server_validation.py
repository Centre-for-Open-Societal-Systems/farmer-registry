"""Server-side enforcement of the intake rules (G2R-47, gaps G2/G3).

Same convention as test_farmer_birth_date_sync.py: imports openg2p_registry_core,
so it runs in the container, not on a bare host checkout.

The rules themselves and their agreement with the form's client-side metadata are
covered by test_validation_rules_match_metadata.py, which is stdlib-only. This
file covers what the domain services *do* with them.
"""

import unittest

from openg2p_registry_core.errors import G2PRegistryException
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_farmer import (
    G2PRegisterDomainServiceFarmer,
)
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_reg_id import (
    G2PRegisterDomainServiceRegId,
)


class TestFarmerNameValidation(unittest.TestCase):
    def setUp(self):
        self.validate = G2PRegisterDomainServiceFarmer()._validate_names

    def test_accepts_amharic_names(self):
        record = {"import_source": "INTAKE_FORM", "first_name": "አበበ", "middle_name": "ሀብታሙ"}
        self.validate(record)
        self.assertEqual(record["first_name"], "አበበ")

    def test_rejects_digits_in_a_name(self):
        record = {"import_source": "INTAKE_FORM", "first_name": "Abebe1", "middle_name": "Kebede"}
        with self.assertRaises(G2PRegistryException) as ctx:
            self.validate(record)
        self.assertIn("first_name", str(ctx.exception))

    def test_trims_surrounding_whitespace(self):
        record = {"import_source": "INTAKE_FORM", "first_name": "  Abebe  ", "middle_name": "Kebede"}
        self.validate(record)
        self.assertEqual(record["first_name"], "Abebe")

    def test_required_names_enforced_on_the_form(self):
        record = {"import_source": "INTAKE_FORM", "first_name": "", "middle_name": "Kebede"}
        with self.assertRaises(G2PRegistryException) as ctx:
            self.validate(record)
        self.assertIn("first_name is required", str(ctx.exception))

    def test_required_names_not_enforced_on_bulk_import(self):
        """~6% of genuine Gen1 farmers have no first name; rejecting them would
        block the migration rather than improve the data."""
        record = {"import_source": "IMPORT_FILE", "first_name": "", "middle_name": ""}
        self.validate(record)  # must not raise

    def test_format_is_still_enforced_on_bulk_import(self):
        """Optional is not the same as unchecked -- a name with digits in it is
        wrong however it arrived."""
        record = {"import_source": "IMPORT_FILE", "first_name": "Abebe1"}
        with self.assertRaises(G2PRegistryException):
            self.validate(record)

    def test_fathers_first_name_required_on_the_form(self):
        """Gen1 parity: the farmer's first name and the father's first name are
        the two mandatory identifiers."""
        record = {"import_source": "INTAKE_FORM", "first_name": "Abebe", "father_first_name": ""}
        with self.assertRaises(G2PRegistryException) as ctx:
            self.validate(record)
        self.assertIn("father_first_name is required", str(ctx.exception))

    def test_middle_name_is_optional(self):
        """The father is captured as his own triple, so the farmer's middle_name no
        longer stands in for him and must not block a save."""
        record = {"import_source": "INTAKE_FORM", "first_name": "Abebe", "middle_name": "", "father_first_name": "Kebede"}
        self.validate(record)  # must not raise

    def test_fathers_other_names_stay_optional(self):
        record = {"import_source": "INTAKE_FORM", "first_name": "Abebe", "father_first_name": "Kebede", "father_middle_name": "", "father_last_name": ""}
        self.validate(record)  # must not raise

    def test_fathers_name_format_is_checked(self):
        record = {"import_source": "INTAKE_FORM", "first_name": "Abebe", "father_first_name": "Kebede2"}
        with self.assertRaises(G2PRegistryException) as ctx:
            self.validate(record)
        self.assertIn("father_first_name", str(ctx.exception))

    def test_grandfather_name_stays_optional(self):
        """Gen1 fill is 26%; parity means it must not block a save."""
        record = {"import_source": "INTAKE_FORM", "first_name": "Abebe", "father_first_name": "Kebede", "last_name": ""}
        self.validate(record)  # must not raise

    def test_absent_key_is_not_a_blank_value(self):
        """A partial update of, say, marital_status carries no name keys at all
        and must not be read as an attempt to clear the name."""
        record = {"import_source": "INTAKE_FORM", "marital_status": "MARRIED"}
        self.validate(record)  # must not raise

    def test_overlong_name_rejected(self):
        record = {"import_source": "INTAKE_FORM", "first_name": "A" * 101, "middle_name": "Kebede"}
        with self.assertRaises(G2PRegistryException) as ctx:
            self.validate(record)
        self.assertIn("100 characters", str(ctx.exception))


class TestRegIdValueValidation(unittest.TestCase):
    def setUp(self):
        self.validate = G2PRegisterDomainServiceRegId()._validate_value_format

    def test_accepts_a_fan_prefixed_value(self):
        record = {"id_type": "FAN", "value": "FAN-123456789012"}
        self.validate(record)
        self.assertEqual(record["value"], "FAN-123456789012")

    def test_rejects_a_malformed_national_id(self):
        record = {"id_type": "UID", "value": "AB-2024-0091"}
        with self.assertRaises(G2PRegistryException) as ctx:
            self.validate(record)
        self.assertIn("UID", str(ctx.exception))

    def test_odk_ack_ids_are_not_format_checked(self):
        """Their value is whatever the ODK submission carried -- odk_client.py
        writes json_data[id_value_key] straight through, and Gen1's id_validation
        is NULL on every id_type. There is no format to assert."""
        record = {"id_type": "FARMER_ODK_ACK_ID", "value": "uuid:9f3c-2024-0091"}
        self.validate(record)  # must not raise

    def test_unregistered_id_type_is_accepted(self):
        record = {"id_type": "OTHER", "value": "anything-at-all"}
        self.validate(record)  # must not raise

    def test_blank_value_is_left_to_the_required_check(self):
        record = {"id_type": "UID", "value": ""}
        self.validate(record)  # must not raise here


if __name__ == "__main__":
    unittest.main()


class TestFarmerBooleanNormalization(unittest.TestCase):
    def setUp(self):
        self.normalize = G2PRegisterDomainServiceFarmer._normalize_booleans

    def test_select_strings_become_booleans(self):
        record = {"disabled": "true", "is_psnp_user": "false"}
        self.normalize(record)
        self.assertIs(record["disabled"], True)
        self.assertIs(record["is_psnp_user"], False)

    def test_unanswered_stays_null_not_no(self):
        """An untouched Yes/No control submits ''. That is "not asked", which
        is distinct from "No" and must reach the nullable column as NULL."""
        record = {"disabled": "", "is_psnp_user": None}
        self.normalize(record)
        self.assertIsNone(record["disabled"])
        self.assertIsNone(record["is_psnp_user"])

    def test_real_booleans_pass_through(self):
        record = {"disabled": False, "has_personal_phone": True}
        self.normalize(record)
        self.assertIs(record["disabled"], False)
        self.assertIs(record["has_personal_phone"], True)

    def test_absent_flags_are_not_added(self):
        """Intake saves one section at a time and the platform persists every
        key in the record, None included. Adding a flag the section never sent
        nulls a column another section owns (disabled / is_psnp_user live in
        Socio-economic, is_household_head in Household) on every unrelated
        save."""
        record = {"first_name": "Abebe", "father_first_name": "Kebede"}
        self.normalize(record)
        self.assertEqual(record, {"first_name": "Abebe", "father_first_name": "Kebede"})
