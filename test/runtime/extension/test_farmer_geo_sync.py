import unittest
from unittest.mock import AsyncMock, patch

from openg2p_registry_core.services import G2PGeoHierarchyService

from openg2p_registry_farmer_extension.register_domain.services import (
    G2PRegisterDomainServiceFarmer,
)


class TestFarmerGeoSync(unittest.IsolatedAsyncioTestCase):
    async def test_later_section_save_preserves_location(self):
        service = G2PRegisterDomainServiceFarmer()
        hierarchy = {"hierarchy": [
            {"level_mnemonic": level, "level_value_mnemonic": name,
             "level_value_id": f"{level}-test"}
            for level, name in (
                ("region", "Tigray"), ("zone", "North Western"),
                ("woreda", "Tahtay Koraro"), ("kebele", "May Adirasha"),
            )
        ]}
        with patch.object(G2PGeoHierarchyService, "get_component") as component:
            component.return_value.get_geo_hierarchy = AsyncMock(return_value=hierarchy)
            stored = {"geo_lowest_level_value_id": "kebele-test"}
            await service._sync_flattened_geo_names(stored)
            self.assertEqual(stored["region_name"], "Tigray")
            self.assertEqual(stored["zone_name"], "North Western")
            self.assertEqual(stored["woreda_name"], "Tahtay Koraro")
            self.assertEqual(stored["kebele_name"], "May Adirasha")
            self.assertEqual(stored["woreda_level_value_id"], "woreda-test")

            # The platform merges each section's validated payload into the row.
            personal_section = {"first_name": "Test"}
            await service._sync_flattened_geo_names(personal_section)
            stored.update(personal_section)
            self.assertEqual(stored["region_name"], "Tigray")
            self.assertEqual(stored["kebele_name"], "May Adirasha")
            component.return_value.get_geo_hierarchy.assert_awaited_once()

    async def test_explicitly_clearing_location_clears_projections(self):
        for empty in (None, ""):
            with self.subTest(empty=empty):
                record = {"geo_lowest_level_value_id": empty, "region_name": "Tigray"}
                await G2PRegisterDomainServiceFarmer()._sync_flattened_geo_names(record)
                for field in ("region_name", "zone_name", "woreda_name", "kebele_name",
                              "woreda_level_value_id"):
                    self.assertIsNone(record[field])
