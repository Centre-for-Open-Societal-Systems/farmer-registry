"""Shared record helpers used by every farmer domain service.

Same convention as test_farmer_birth_date_sync.py: imports openg2p_registry_core,
so it runs in the container, not on a bare host checkout.
"""

import unittest
from datetime import date

from openg2p_registry_core.errors import G2PRegistryException
from openg2p_registry_farmer_extension.register_domain.services.domain_validation_utils import (
    normalize_coordinates,
    sync_ethiopic_date_pair,
)


class TestNormalizeCoordinates(unittest.TestCase):
    """The platform stores coordinates as VARCHAR while the form submits floats;
    asyncpg refused the float and every Location save died with SYS-ERR-001."""

    def test_floats_become_canonical_strings(self):
        record = {"latitude": 9.03, "longitude": 38.7469}
        normalize_coordinates(record)
        self.assertEqual(record, {"latitude": "9.03", "longitude": "38.7469"})

    def test_numeric_strings_are_kept_as_strings(self):
        record = {"latitude": "9.0300000", "longitude": "-0.5"}
        normalize_coordinates(record)
        self.assertEqual(record, {"latitude": "9.03", "longitude": "-0.5"})

    def test_blank_clears_and_absent_is_untouched(self):
        record = {"latitude": "", "name": "x"}
        normalize_coordinates(record)
        self.assertEqual(record, {"latitude": None, "name": "x"})

    def test_out_of_range_is_named_in_form_words(self):
        with self.assertRaises(G2PRegistryException) as ctx:
            normalize_coordinates({"latitude": 91})
        self.assertIn("Latitude must be between -90 and 90", str(ctx.exception))
        with self.assertRaises(G2PRegistryException) as ctx:
            normalize_coordinates({"longitude": -181})
        self.assertIn("Longitude must be between -180 and 180", str(ctx.exception))

    def test_non_numeric_is_rejected(self):
        with self.assertRaises(G2PRegistryException) as ctx:
            normalize_coordinates({"longitude": "east"})
        self.assertIn("Longitude must be a number", str(ctx.exception))


class TestSyncEthiopicDatePair(unittest.TestCase):
    """The helper behind birth_date_ec (farmer, household member),
    planted_date_ec (crop) and expiry_date_ec (ID)."""

    def test_gregorian_fills_ethiopic(self):
        record = {"planted_date": date(2024, 9, 11)}
        sync_ethiopic_date_pair(record, "planted_date", "planted_date_ec", "Planted Date")
        self.assertEqual(record["planted_date_ec"], "2017-01-01")

    def test_ethiopic_fills_gregorian(self):
        record = {"expiry_date_ec": "2017-01-01"}
        sync_ethiopic_date_pair(record, "expiry_date", "expiry_date_ec", "Expiry Date")
        self.assertEqual(record["expiry_date"], date(2024, 9, 11))

    def test_pagumen_is_a_real_day(self):
        record = {"birth_date_ec": "2015-13-05"}
        sync_ethiopic_date_pair(record, "birth_date", "birth_date_ec", "Date of birth")
        self.assertEqual(record["birth_date"], date(2023, 9, 10))

    def test_conflict_names_both_calendars(self):
        record = {"birth_date": date(1990, 5, 15), "birth_date_ec": "1983-09-07"}
        with self.assertRaises(G2PRegistryException) as ctx:
            sync_ethiopic_date_pair(record, "birth_date", "birth_date_ec", "Date of birth")
        self.assertIn("Date of birth (EC) does not match Date of birth (GC)", str(ctx.exception))

    def test_malformed_ethiopic_says_what_shape_is_expected(self):
        with self.assertRaises(G2PRegistryException) as ctx:
            sync_ethiopic_date_pair({"birth_date_ec": "15/09/1982"}, "birth_date", "birth_date_ec", "Date of birth")
        self.assertIn("YYYY-MM-DD", str(ctx.exception))

    def test_both_blank_store_null(self):
        record = {"planted_date": "", "planted_date_ec": ""}
        sync_ethiopic_date_pair(record, "planted_date", "planted_date_ec", "Planted Date")
        self.assertEqual(record, {"planted_date": None, "planted_date_ec": None})

    def test_absent_pair_is_untouched(self):
        record = {"commodity": "TEFF"}
        sync_ethiopic_date_pair(record, "planted_date", "planted_date_ec", "Planted Date")
        self.assertEqual(record, {"commodity": "TEFF"})
