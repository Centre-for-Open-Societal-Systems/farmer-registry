"""G2R-334: validate the Farmer form's optional livestock section."""
import unittest
from openg2p_registry_core.errors import G2PRegistryException
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_livestock import G2PRegisterDomainServiceLivestock

class TestLivestockRows(unittest.IsolatedAsyncioTestCase):
    async def validate(self, rows):
        await G2PRegisterDomainServiceLivestock().validate_domain_attributes(rows)
        return rows

    async def rejected(self, row, message):
        with self.assertRaises(G2PRegistryException) as error:
            await self.validate([row])
        self.assertIn(message, str(error.exception))

    async def test_empty_section_is_optional(self):
        await self.validate([])

    async def test_blank_row_is_not_a_livestock_record(self):
        await self.rejected({}, "Livestock Type is required")

    async def test_missing_or_whitespace_type_is_rejected(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                await self.rejected({"livestock_type": value, "head_count": 2}, "Livestock Type is required")

    async def test_missing_count_is_rejected(self):
        for row in ({"livestock_type": "CATTLE"}, {"livestock_type": "CATTLE", "head_count": None}, {"livestock_type": "CATTLE", "head_count": " "}):
            with self.subTest(row=row):
                await self.rejected(row, "Head Count is required")

    async def test_zero_count_and_optional_fields(self):
        rows=await self.validate([{"livestock_type": " CATTLE ", "head_count": 0}])
        self.assertEqual(rows[0]["head_count"], 0)
        self.assertEqual(rows[0]["livestock_type"], "CATTLE")

    async def test_count_is_normalized_for_database_integer(self):
        for value in (3, "3", 3.0):
            with self.subTest(value=value):
                rows=await self.validate([{"livestock_type": "CATTLE", "head_count": value}])
                self.assertIs(type(rows[0]["head_count"]), int)
                self.assertEqual(rows[0]["head_count"], 3)

    async def test_invalid_counts_are_not_silently_truncated(self):
        for value in (-1, 1.5, "1.5", True, "abc", float("nan"), float("inf"), 2147483648):
            with self.subTest(value=value):
                await self.rejected({"livestock_type": "CATTLE", "head_count": value}, "Head Count")

    async def test_removed_blank_rows_do_not_block_save(self):
        await self.validate([{"edit_action":"DELETE"}, {"livestock_type":"CATTLE", "head_count":2}])

    async def test_readding_a_removed_type_is_allowed(self):
        await self.validate([{"edit_action":"DELETE", "livestock_type":"CATTLE"}, {"livestock_type":"CATTLE", "head_count":2}])

    async def test_duplicate_types_still_fail(self):
        with self.assertRaises(G2PRegistryException) as error:
            await self.validate([{"livestock_type":"CATTLE", "head_count":2}, {"livestock_type":" CATTLE ", "head_count":3}])
        self.assertIn("same Livestock Type",str(error.exception))

    async def test_legacy_import_missing_optional_data_remains_accepted(self):
        for source in ("IMPORT_FILE", "PARTNER"):
            await self.validate([{"import_source":source,"livestock_type":"CATTLE"}])
            rows = await self.validate([{"import_source":source,"livestock_type":"CATTLE", "head_count":""}])
            self.assertIsNone(rows[0]["head_count"])

    async def test_explicit_interactive_sources_require_count(self):
        for source in ("INTAKE_FORM", "STAFF_PORTAL", "AGENT_PORTAL"):
            await self.rejected({"import_source":source,"livestock_type":"CATTLE"}, "Head Count is required")

if __name__ == "__main__": unittest.main()
