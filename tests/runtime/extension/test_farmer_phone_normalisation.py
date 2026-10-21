"""What the farmer phone service does with a number (item 8 of the SRS review).

Same convention as test_intake_server_validation.py: imports
openg2p_registry_core, so it runs in the container, not on a bare host checkout.
The pattern and the normaliser themselves are covered stdlib-only in
test_validation_rules_match_metadata.py.
"""

import asyncio
import types
import unittest

from openg2p_registry_core.errors import G2PRegistryException
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_farmer_phone import (
    FARMER_PHONE_REGISTER_ID,
    G2PRegisterDomainServiceFarmerPhone,
)


def _validate(records):
    asyncio.run(G2PRegisterDomainServiceFarmerPhone().validate_domain_attributes(records))
    return records


class TestPhoneValidation(unittest.TestCase):
    def test_every_form_is_stored_as_the_national_number(self):
        for raw in ("0912345678", "912345678", "+251912345678", "251912345678", "+251 91 234 5678"):
            with self.subTest(raw=raw):
                (record,) = _validate([{"phone_type": "PRIMARY", "phone_number": raw, "is_primary": True}])
                self.assertEqual(record["phone_number"], "912345678")
                self.assertEqual(record["phone_e164"], "+251912345678")
                self.assertEqual(record["country_code"], "ETH")

    def test_an_explicit_country_code_is_kept(self):
        (record,) = _validate([{"phone_type": "PRIMARY", "phone_number": "0912345678", "country_code": "ET"}])
        self.assertEqual(record["country_code"], "ET")

    def test_junk_is_rejected_with_both_forms_in_the_message(self):
        with self.assertRaises(G2PRegistryException) as ctx:
            _validate([{"phone_type": "PRIMARY", "phone_number": "12345"}])
        self.assertIn("+251912345678", str(ctx.exception))

    def test_deleted_rows_are_not_validated(self):
        records = _validate([{"phone_type": "OTHER", "phone_number": "junk", "edit_action": "DELETE"}])
        self.assertEqual(records[0]["phone_number"], "junk")


class TestPhoneIngest(unittest.TestCase):
    """Partner and ODK payloads can reach the register without the form's
    validation, so post_ingest normalises the row that landed."""

    def _ingest(self, phone_number, country_code=None):
        row = types.SimpleNamespace(
            phone_number=phone_number,
            phone_e164=None,
            country_code=country_code,
            link_internal_record_id=None,  # skips the projection sync
            internal_record_id="p1",
            is_primary=True,
        )
        asyncio.run(G2PRegisterDomainServiceFarmerPhone().post_ingest(FARMER_PHONE_REGISTER_ID, row, session=None))
        return row

    def test_gen1_e164_is_split(self):
        row = self._ingest("+251911223344")
        self.assertEqual((row.phone_number, row.phone_e164, row.country_code), ("911223344", "+251911223344", "ETH"))

    def test_unrecognised_value_is_left_as_sent(self):
        row = self._ingest("n/a")
        self.assertEqual((row.phone_number, row.phone_e164), ("n/a", None))


if __name__ == "__main__":
    unittest.main()
