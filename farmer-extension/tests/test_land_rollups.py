"""The farmer's land rollups (total / owned / rented / crop-sharing area and
ownership) must follow a land whichever way it arrives.

Until 18 Sep they were recomputed only from post_approve, i.e. when a land
CHANGE REQUEST was approved. A land registered through the intake form is
inserted by the ingest worker, which calls post_ingest instead -- and the land
service had no post_ingest, so every farmer registered with lands showed an
empty Lands summary until someone edited a land.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_land import (
    LAND_REGISTER_ID,
    G2PRegisterDomainServiceLand,
)


class _Session:
    """Just enough of an AsyncSession for _recompute_farmer_land_rollups:
    the first execute returns the land row, the second the farmer's lands,
    the third (the UPDATE) is captured."""

    def __init__(self, land_row, all_lands):
        self._results = [
            SimpleNamespace(scalar=lambda: land_row),
            SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: all_lands)),
        ]
        self.statements = []

    async def execute(self, statement):
        if self._results:
            return self._results.pop(0)
        self.statements.append(statement)
        return SimpleNamespace()


def _land(ownership, size, unit="HECTARE"):
    return SimpleNamespace(
        land_ownership_type=ownership, land_size=size, unit=unit, record_status="ACTIVE"
    )


class TestPostIngest(unittest.IsolatedAsyncioTestCase):
    async def test_other_registers_are_ignored(self):
        service = G2PRegisterDomainServiceLand()
        with patch.object(
            service, "_recompute_farmer_land_rollups", new=AsyncMock()
        ) as recompute:
            await service.post_ingest("not-the-land-register", SimpleNamespace(), object())
        recompute.assert_not_awaited()

    async def test_land_ingest_recomputes_the_farmer(self):
        service = G2PRegisterDomainServiceLand()
        session = object()
        with patch.object(
            service, "_recompute_farmer_land_rollups", new=AsyncMock()
        ) as recompute:
            await service.post_ingest(
                LAND_REGISTER_ID, SimpleNamespace(internal_record_id="land-1"), session
            )
        recompute.assert_awaited_once_with("land-1", session)


class TestRollupArithmetic(unittest.IsolatedAsyncioTestCase):
    async def _values(self, lands):
        service = G2PRegisterDomainServiceLand()
        session = _Session(
            SimpleNamespace(link_internal_record_id="farmer-1"), lands
        )
        await service._recompute_farmer_land_rollups("land-1", session)
        self.assertEqual(len(session.statements), 1, "exactly one farmer UPDATE")
        update = session.statements[0]
        # SQLAlchemy compiles .values(...) into named bind parameters keyed by
        # column name (the WHERE bind gets a numbered suffix).
        return dict(update.compile().params)

    async def test_owner_and_tenant_make_hybrid_and_sum_in_hectares(self):
        values = await self._values(
            [_land("OWNER", 2.0), _land("TENANT", 1.0, unit="ACRE"), _land("CROP_SHARE", 0.5)]
        )
        got = values
        self.assertEqual(got["total_land_owned_area"], 2.0)
        self.assertEqual(got["total_land_rent_area"], 0.404686)
        self.assertEqual(got["total_land_crop_sharing_area"], 0.5)
        self.assertEqual(got["total_land_area"], 2.904686)
        self.assertEqual(got["land_ownership"], "HYBRID")

    async def test_single_owner_is_owner(self):
        values = await self._values([_land("OWNER", 54.0)])
        got = values
        self.assertEqual(got["total_land_area"], 54.0)
        self.assertEqual(got["land_ownership"], "OWNER")


if __name__ == "__main__":
    unittest.main()
