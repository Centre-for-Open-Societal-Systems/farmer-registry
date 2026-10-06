"""Server-side checks behind the Add Farmer intake form.

Same convention as test_intake_server_validation.py: imports
openg2p_registry_core, so it runs in the staff-api container, not on a bare
host checkout. One class per rule, so a run reads as a per-rule report.

Each check is exercised through validate_domain_attributes -- the hook both the
intake-form save and the change-request path call with the section's whole
table -- rather than through the private helper, so a check that is written but
never wired in fails here.
"""

import unittest
from datetime import date, timedelta

from openg2p_registry_core.errors import G2PRegistryException
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_crop import (
    G2PRegisterDomainServiceCrop,
)
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_farmer import (
    G2PRegisterDomainServiceFarmer,
)
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_farmer_phone import (
    G2PRegisterDomainServiceFarmerPhone,
)
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_land import (
    G2PRegisterDomainServiceLand,
)
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_reg_id import (
    G2PRegisterDomainServiceRegId,
)

FIN = "123456789012"
FAN = "1234567890123456"
RID = "10001100010001020240101120000"  # 29 digits


class _Case(unittest.IsolatedAsyncioTestCase):
    service = None

    async def accepts(self, records):
        await self.service().validate_domain_attributes(records)
        return records

    async def rejects(self, records, *fragments):
        with self.assertRaises(G2PRegistryException) as ctx:
            await self.service().validate_domain_attributes(records)
        for fragment in fragments:
            self.assertIn(fragment, str(ctx.exception))


class TestBlankIdValue(_Case):
    service = G2PRegisterDomainServiceRegId

    async def test_spaces_only_value_is_refused(self):
        await self.rejects([{"id_type": "UID", "value": "    ", "status": "VALID"}], "ID Value is required")

    async def test_value_is_trimmed(self):
        records = await self.accepts([{"id_type": "UID", "value": f"  {FIN} ", "status": "VALID"}])
        self.assertEqual(records[0]["value"], FIN)


class TestDuplicateId(_Case):
    service = G2PRegisterDomainServiceRegId

    async def test_same_uid_as_valid_and_invalid_is_refused(self):
        await self.rejects(
            [
                {"id_type": "UID", "value": FIN, "status": "VALID"},
                {"id_type": "UID", "value": FIN, "status": "INVALID"},
            ],
            "same ID is listed more than once",
        )

    async def test_fan_with_and_without_prefix_is_the_same_id(self):
        await self.rejects(
            [{"id_type": "UID", "value": FAN}, {"id_type": "UID", "value": f"FAN-{FAN}"}],
            "same ID",
        )

    async def test_different_uids_are_accepted(self):
        await self.accepts([{"id_type": "UID", "value": FIN}, {"id_type": "UID", "value": FAN}])

    async def test_a_deleted_row_does_not_count(self):
        await self.accepts(
            [
                {"id_type": "UID", "value": FIN, "status": "VALID", "edit_action": "DELETE"},
                {"id_type": "UID", "value": FIN, "status": "INVALID"},
            ]
        )


class TestIdFormatPerType(_Case):
    service = G2PRegisterDomainServiceRegId

    async def test_rid_refuses_a_uid_formatted_value(self):
        await self.rejects([{"id_type": "RID", "value": FIN}], "not a valid RID", "29-digit")

    async def test_rid_accepts_a_29_digit_registration_id(self):
        await self.accepts([{"id_type": "RID", "value": RID}])

    async def test_uid_accepts_fin_and_fan(self):
        await self.accepts([{"id_type": "UID", "value": FIN}])
        await self.accepts([{"id_type": "UID", "value": FAN}])
        await self.accepts([{"id_type": "UID", "value": f"FAN-{FAN}"}])

    async def test_uid_refuses_a_rid_and_other_lengths(self):
        for value in (RID, "1234567890123", "ET-NID-100001"):
            with self.subTest(value=value):
                await self.rejects([{"id_type": "UID", "value": value}], "not a valid UID")


class TestExpiredIdCannotBeValid(_Case):
    service = G2PRegisterDomainServiceRegId

    async def test_expired_id_marked_valid_is_refused(self):
        await self.rejects(
            [{"id_type": "UID", "value": FIN, "status": "VALID", "expiry_date": "2018-09-26"}],
            "expired on 2018-09-26",
            "Status cannot be Valid",
        )

    async def test_expired_id_marked_invalid_is_accepted(self):
        await self.accepts([{"id_type": "UID", "value": FIN, "status": "INVALID", "expiry_date": "2018-09-26"}])

    async def test_unexpired_valid_id_is_accepted(self):
        future = (date.today() + timedelta(days=365)).isoformat()
        await self.accepts([{"id_type": "UID", "value": FIN, "status": "VALID", "expiry_date": future}])

    async def test_expiry_entered_in_ethiopic_only_is_checked_too(self):
        # 2010-01-17 EC is 2017-09-27 GC: derived first, then checked.
        await self.rejects(
            [{"id_type": "UID", "value": FIN, "status": "VALID", "expiry_date_ec": "2010-01-17"}],
            "Status cannot be Valid",
        )


class TestCoordinateBounds(_Case):
    """Already enforced server-side before this change; pinned here because QA
    reported 2100 / 788 as accepted."""

    service = G2PRegisterDomainServiceFarmer

    async def test_out_of_range_longitude_and_latitude_are_refused(self):
        await self.rejects([{"longitude": "2100", "latitude": "9.03"}], "Longitude must be between -180 and 180")
        await self.rejects([{"longitude": "38.74", "latitude": "788"}], "Latitude must be between -90 and 90")


class TestDuplicatePhone(_Case):
    service = G2PRegisterDomainServiceFarmerPhone

    async def test_same_number_under_two_phone_types_is_refused(self):
        await self.rejects(
            [
                {"phone_type": "PRIMARY", "phone_number": "0123456780", "is_primary": True},
                {"phone_type": "SECONDARY", "phone_number": "0123456780"},
            ],
            "same Phone Number is listed more than once",
        )

    async def test_trunk_zero_does_not_make_it_a_different_number(self):
        await self.rejects(
            [
                {"phone_type": "PRIMARY", "phone_number": "0912345678"},
                {"phone_type": "OTHER", "phone_number": "912345678"},
            ],
            "same Phone Number",
        )

    async def test_international_form_is_the_same_number(self):
        await self.rejects(
            [
                {"phone_type": "PRIMARY", "phone_number": "+251912345678"},
                {"phone_type": "SECONDARY", "phone_number": "0912345678"},
            ],
            "same Phone Number",
        )

    async def test_two_different_numbers_are_accepted(self):
        await self.accepts(
            [
                {"phone_type": "PRIMARY", "phone_number": "0912345678", "is_primary": True},
                {"phone_type": "SECONDARY", "phone_number": "0912345679"},
            ]
        )


class TestDuplicateLandId(_Case):
    service = G2PRegisterDomainServiceLand

    async def test_same_land_id_twice_is_refused(self):
        await self.rejects([{"land_id": "LAN-001"}, {"land_id": "LAN-001"}], "same Land ID is listed more than once")

    async def test_comparison_ignores_case_and_spacing(self):
        await self.rejects([{"land_id": "LAN-001"}, {"land_id": " lan-001 "}], "same Land ID")

    async def test_distinct_and_blank_land_ids_are_accepted(self):
        await self.accepts([{"land_id": "LAN-001"}, {"land_id": "LAN-002"}, {"land_id": ""}, {"land_id": None}])


class TestLandCertificateReplace(_Case):
    service = G2PRegisterDomainServiceLand

    async def test_an_existing_document_id_passes_through_untouched(self):
        records = await self.accepts([{"land_id": "LAN-001", "certificate_storage_id": "doc-old"}])
        self.assertEqual(records[0]["certificate_storage_id"], "doc-old")
        self.assertTrue(records[0]["certificate_provided"])


class TestDuplicateCommodityPerSeason(_Case):
    service = G2PRegisterDomainServiceCrop

    async def test_same_commodity_in_two_seasons_is_accepted(self):
        # Meher and Belg double-cropping is legitimate.
        await self.accepts(
            [
                {"commodity": "TEFF", "season": "MEHER", "planted_date": "2025-07-01"},
                {"commodity": "TEFF", "season": "BELG", "planted_date": "2025-03-01"},
            ]
        )

    async def test_same_commodity_twice_in_one_season_is_refused(self):
        await self.rejects(
            [
                {"commodity": "TEFF", "season": "MEHER", "planted_date": "2025-07-01"},
                {"commodity": "teff", "season": "MEHER", "planted_date": "2025-08-01"},
            ],
            "same Commodity is listed more than once for the same Season",
        )

    async def test_a_deleted_row_does_not_count(self):
        await self.accepts(
            [
                {"commodity": "TEFF", "season": "MEHER", "edit_action": "DELETE"},
                {"commodity": "TEFF", "season": "MEHER"},
            ]
        )


class TestBlankCrop(_Case):
    service = G2PRegisterDomainServiceCrop

    async def test_spaces_only_commodity_is_refused(self):
        await self.rejects([{"commodity": "   ", "season": "MEHER"}], "Commodity is required")

    async def test_blank_season_is_refused(self):
        await self.rejects([{"commodity": "TEFF", "season": ""}], "Season is required")

    async def test_values_are_trimmed(self):
        records = await self.accepts([{"commodity": " TEFF ", "season": " MEHER "}])
        self.assertEqual((records[0]["commodity"], records[0]["season"]), ("TEFF", "MEHER"))

    async def test_bulk_import_rows_are_not_required_checked(self):
        await self.accepts([{"import_source": "IMPORT_FILE", "commodity": "", "season": ""}])


if __name__ == "__main__":
    unittest.main()
