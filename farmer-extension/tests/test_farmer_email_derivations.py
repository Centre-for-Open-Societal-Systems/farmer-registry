"""The farmer's email on save and after ingest (services/derivations.py). They
need the registry platform, so they run inside the staff API image and are
skipped elsewhere."""

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("openg2p_registry_core")

from openg2p_registry_core.errors import G2PRegistryException
from openg2p_registry_farmer_extension.register_domain.services import derivations


def test_a_bad_typed_email_refuses_the_farmer_record():
    with pytest.raises(G2PRegistryException) as error:
        derivations._farmer_record({"email": "name@"})
    assert "Email: enter an address like name@example.org" in error.value.message


def test_a_typed_email_fills_the_emails_list_on_save():
    record = {"email": "Abebe@Example.org"}
    derivations._farmer_record(record)
    assert record["emails"] == [{"address": "abebe@example.org", "is_primary": True}]


def test_an_ingested_farmer_gets_its_email_from_the_emails_list(monkeypatch):
    async def nothing(*args, **kwargs):
        return None

    monkeypatch.setattr(derivations.Derivations, "post_ingest", lambda self, *a: nothing(), raising=False)
    monkeypatch.setattr(derivations, "_phones_from_list", nothing)
    monkeypatch.setattr(derivations, "refresh_farmer", nothing)
    row = SimpleNamespace(geo_code_hierarchy_json=None, enumerator_name="odk", created_by="odk",
                          data_collection_date=None, created_at=None, internal_record_id="r-1",
                          email=None, emails=[{"address": "odk@example.org", "is_primary": True}])
    asyncio.run(derivations.FarmerDerivations().post_ingest("farmer", row, None))
    assert row.email == "odk@example.org"
