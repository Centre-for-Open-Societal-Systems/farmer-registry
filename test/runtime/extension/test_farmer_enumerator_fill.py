"""Who collected a farmer, and when, comes from the intake submission.

The web intake form renders only its first tab, so the Enumerator tab's
fields were never typed in and every farmer's Enumerator tab was empty; and
post_ingest stamped every ingested farmer import_source PARTNER, web intake
included. Both now read off the submission the farmer was ingested from.
"""

import unittest
from datetime import date, datetime
from types import SimpleNamespace

from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_farmer import (
    G2PRegisterDomainServiceFarmer,
)


def _row(**kw):
    base = dict(enumerator_name=None, data_collection_date=None, import_source=None)
    base.update(kw)
    return SimpleNamespace(**base)


class TestImportSource(unittest.TestCase):
    def test_web_intake_is_intake_form(self):
        self.assertEqual(
            G2PRegisterDomainServiceFarmer._import_source_of(SimpleNamespace(submission_source="STAFF_PORTAL")),
            "INTAKE_FORM",
        )

    def test_partner_and_unknown_are_partner(self):
        for source in ("PARTNER", "", None):
            with self.subTest(source=source):
                self.assertEqual(
                    G2PRegisterDomainServiceFarmer._import_source_of(SimpleNamespace(submission_source=source)),
                    "PARTNER",
                )
        self.assertEqual(G2PRegisterDomainServiceFarmer._import_source_of(None), "PARTNER")


class TestEnumeratorFill(unittest.TestCase):
    def test_filled_from_the_submission(self):
        row = _row()
        G2PRegisterDomainServiceFarmer._fill_enumerator(
            row, SimpleNamespace(created_by="Staff Admin", first_created_at=datetime(2026, 9, 21, 6, 14), finalized_at=None)
        )
        self.assertEqual(row.enumerator_name, "Staff Admin")
        self.assertEqual(row.data_collection_date, date(2026, 9, 21))

    def test_payload_values_are_kept(self):
        row = _row(enumerator_name="Abebe K.", data_collection_date=date(2026, 9, 1))
        G2PRegisterDomainServiceFarmer._fill_enumerator(
            row, SimpleNamespace(created_by="Staff Admin", first_created_at=datetime(2026, 9, 21), finalized_at=None)
        )
        self.assertEqual(row.enumerator_name, "Abebe K.")
        self.assertEqual(row.data_collection_date, date(2026, 9, 1))

    def test_no_submission_changes_nothing(self):
        row = _row()
        G2PRegisterDomainServiceFarmer._fill_enumerator(row, None)
        self.assertIsNone(row.enumerator_name)
        self.assertIsNone(row.data_collection_date)


if __name__ == "__main__":
    unittest.main()
