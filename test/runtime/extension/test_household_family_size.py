"""Family size is calculated at the domain boundary for intake and imports."""
import unittest

from openg2p_registry_core.errors import G2PRegistryException
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_household import G2PRegisterDomainServiceHousehold


class TestDerivedFamilySize(unittest.IsolatedAsyncioTestCase):
    async def validate(self, **fields):
        await G2PRegisterDomainServiceHousehold().validate_domain_attributes([fields])
        return fields

    async def test_derives_and_overrides_stale_client_total(self):
        row = await self.validate(number_of_male_members="2", number_of_female_members="3", size_of_group=99, number_of_children=2)
        self.assertEqual(row["size_of_group"], 5)
        self.assertEqual(row["number_of_male_members"], 2)

    async def test_explicit_zero_is_a_valid_count(self):
        row = await self.validate(number_of_male_members=0, number_of_female_members=0)
        self.assertEqual(row["size_of_group"], 0)

    async def test_blank_count_contributes_zero(self):
        row = await self.validate(number_of_male_members="", number_of_female_members=3)
        self.assertEqual(row["size_of_group"], 3)

    async def test_unknown_counts_do_not_fabricate_a_total(self):
        row = await self.validate(number_of_male_members="", number_of_female_members=None)
        self.assertIsNone(row["size_of_group"])

    async def test_unrelated_section_does_not_overwrite_total(self):
        row = await self.validate(address_line_1="Example")
        self.assertNotIn("size_of_group", row)

    async def test_independent_client_total_is_not_accepted(self):
        row = await self.validate(size_of_group=99)
        self.assertNotIn("size_of_group", row)

    async def test_negative_counts_are_rejected(self):
        with self.assertRaises(G2PRegistryException):
            await self.validate(number_of_male_members=-1, number_of_female_members=3)

    async def test_children_cannot_exceed_derived_total(self):
        with self.assertRaises(G2PRegistryException):
            await self.validate(number_of_male_members=1, number_of_female_members=1, number_of_children=3)

    async def test_parents_are_not_counted_twice(self):
        row = await self.validate(number_of_male_members=2, number_of_female_members=3, father_included=True, mother_included=True)
        self.assertEqual(row["size_of_group"], 5)
