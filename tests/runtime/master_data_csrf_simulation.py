"""Run the actual pinned core client against the local Postman simulation.

MDS_SIM_URL must point to the /mds route. The platform image is required.
"""
import asyncio
import os
from types import SimpleNamespace
import unittest

from openg2p_registry_core.helpers.master_data import MasterDataClient


@unittest.skipUnless(os.environ.get("MDS_SIM_URL"), "Start master-data-csrf.sim.yaml first")
class MasterDataCsrf(unittest.IsolatedAsyncioTestCase):
    def client(self, secret="synthetic-secret"):
        base = os.environ["MDS_SIM_URL"].rstrip("/")
        client = MasterDataClient()
        settings = SimpleNamespace(master_data_api_url=base, master_data_token_url=base + "/token",
                                   master_data_client_id="farmer-test", master_data_client_secret=secret,
                                   master_data_cache_seconds=300, master_data_timeout_seconds=3)
        client._settings = lambda: settings
        return client

    async def test_hierarchy_uses_matching_csrf_and_keeps_cache(self):
        client = self.client()
        result = await client.get_geo_hierarchy("kebele-TEST")
        self.assertEqual([r["level_mnemonic"] for r in result["hierarchy"]], ["region", "zone", "woreda", "kebele"])
        cached = client._geo_index
        self.assertEqual(await client.get_geo_hierarchy("kebele-TEST"), result)
        self.assertIs(client._geo_index, cached)

    async def test_denied_request_stays_denied(self):
        with self.assertRaises(Exception):
            await self.client()._post("/denied")

    async def test_wrong_credentials_do_not_load_locations(self):
        self.assertIsNone(await self.client("wrong-synthetic-secret").get_geo_hierarchy("kebele-TEST"))

    async def test_401_refresh_preserves_csrf(self):
        self.assertEqual(await self.client()._post("/refresh-once"), {"ok": True})


if __name__ == "__main__":
    unittest.main()
