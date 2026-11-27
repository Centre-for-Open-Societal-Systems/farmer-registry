"""The farmer's plot count and mobile number on every save (refresh_farmer in
services/derivations.py). They need the registry platform, so they run inside
the staff API image and are skipped elsewhere."""

import asyncio
from datetime import date, datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("openg2p_registry_core")

from openg2p_registry_oan_farmer_extension.register_domain.services import derivations


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return self


class _Session:
    """The farmer, then its active land rows, then its active phone rows."""

    def __init__(self, farmer, lands, phones):
        self.farmer, self.results = farmer, [_Result(lands), _Result(phones)]

    async def get(self, model, key):
        return self.farmer

    async def execute(self, statement):
        return self.results.pop(0)


def _farmer(**values):
    values = {"registration_date": None, "last_approved_at": None, "created_at": None, **values}
    return SimpleNamespace(internal_record_id="f-1", phone_numbers=None, has_personal_phone=None, **values)


def test_plots_and_mobile_number_follow_the_rows():
    farmer = _farmer()
    phones = [SimpleNamespace(phone_type="MOBILE", phone_e164="+251911000001", phone_number="911000001"),
              SimpleNamespace(phone_type="OTHER", phone_e164=None, phone_number="911000002")]
    lands = [("OWNER", 2, "HECTARE"), ("TENANT", None, None)]
    asyncio.run(derivations.refresh_farmer(_Session(farmer, lands, phones), "f-1"))
    assert farmer.total_plots == 2
    assert farmer.total_land_area == 2
    assert farmer.primary_phone_number == "+251911000001"


def test_a_farmer_without_rows_keeps_its_partner_phone_list():
    farmer = _farmer()
    farmer.phone_numbers = [{"type": "mobile", "number": "+251911000003", "is_primary": True}]
    asyncio.run(derivations.refresh_farmer(_Session(farmer, [], []), "f-1"))
    assert farmer.total_plots == 0
    assert farmer.primary_phone_number == "+251911000003"


def test_registration_date_is_the_day_of_approval():
    farmer = _farmer(last_approved_at=datetime(2026, 11, 17, 6, 6), created_at=datetime(2026, 11, 10, 9, 0))
    asyncio.run(derivations.refresh_farmer(_Session(farmer, [], []), "f-1"))
    assert farmer.registration_date == date(2026, 11, 17)


def test_registration_date_falls_back_to_the_creation_day():
    farmer = _farmer(created_at=datetime(2026, 11, 10, 9, 0))
    asyncio.run(derivations.refresh_farmer(_Session(farmer, [], []), "f-1"))
    assert farmer.registration_date == date(2026, 11, 10)


def test_a_later_approval_never_moves_the_registration_date():
    farmer = _farmer(registration_date=date(2026, 10, 30), last_approved_at=datetime(2026, 11, 17, 6, 6))
    asyncio.run(derivations.refresh_farmer(_Session(farmer, [], []), "f-1"))
    assert farmer.registration_date == date(2026, 10, 30)
