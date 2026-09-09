import unittest
from datetime import date

from openg2p_registry_core.errors import G2PRegistryException

from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_farmer import (
    G2PRegisterDomainServiceFarmer,
)


class TestEthiopianBirthDateSync(unittest.TestCase):
    def setUp(self):
        self.service = G2PRegisterDomainServiceFarmer()
        self.sync = self.service._sync_ethiopian_birth_date

    def test_gregorian_fills_ethiopic(self):
        record = {"birth_date": date(1990, 5, 15)}
        self.sync(record)
        self.assertEqual(record["birth_date_ec"], "1982-09-07")

    def test_ethiopic_fills_gregorian(self):
        record = {"birth_date_ec": "1982-09-07"}
        self.sync(record)
        self.assertEqual(record["birth_date"], date(1990, 5, 15))

    def test_pagumen_round_trips(self):
        record = {"birth_date": date(2023, 9, 10)}
        self.sync(record)
        self.assertEqual(record["birth_date_ec"], "2015-13-05")

        back = {"birth_date_ec": "2015-13-05"}
        self.sync(back)
        self.assertEqual(back["birth_date"], date(2023, 9, 10))

    def test_agreeing_pair_is_kept_and_normalized(self):
        record = {"birth_date": date(1990, 5, 15), "birth_date_ec": "1982-09-07"}
        self.sync(record)
        self.assertEqual(record["birth_date"], date(1990, 5, 15))
        self.assertEqual(record["birth_date_ec"], "1982-09-07")

    def test_conflicting_pair_is_rejected(self):
        record = {"birth_date": date(1990, 5, 15), "birth_date_ec": "1983-09-07"}
        with self.assertRaises(G2PRegistryException) as ctx:
            self.sync(record)
        self.assertIn("does not match birth_date", str(ctx.exception))

    def test_malformed_ethiopic_is_rejected(self):
        record = {"birth_date_ec": "15/09/1982"}
        with self.assertRaises(G2PRegistryException):
            self.sync(record)

    def test_impossible_ethiopic_is_rejected(self):
        # Pagumen 6 only exists in a leap year; 2016 EC is not one.
        record = {"birth_date_ec": "2016-13-06"}
        with self.assertRaises(G2PRegistryException):
            self.sync(record)

    def test_partial_update_without_either_key_is_untouched(self):
        record = {"marital_status": "MARRIED"}
        self.sync(record)
        self.assertNotIn("birth_date", record)
        self.assertNotIn("birth_date_ec", record)

    def test_empty_values_do_not_derive(self):
        record = {"birth_date": "", "birth_date_ec": ""}
        self.sync(record)
        self.assertIn(record.get("birth_date"), ("", None))
        self.assertIn(record.get("birth_date_ec"), ("", None))

    def test_legacy_date_value_is_normalized_to_string(self):
        # Rows written while birth_date_ec was still a DATE column.
        record = {"birth_date_ec": date(1982, 9, 7)}
        self.sync(record)
        self.assertEqual(record["birth_date_ec"], "1982-09-07")
        self.assertEqual(record["birth_date"], date(1990, 5, 15))


if __name__ == "__main__":
    unittest.main()
