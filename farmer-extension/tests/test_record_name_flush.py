"""The stored record name of rows flushed through the platform's own ORM.

Core sets record_name from listeners it registers when the mappers are
configured, so the readable name must win whatever order the listeners run in.
These tests flush real rows (sqlite, with the Postgres-only column types
compiled as JSON) and read back what was stored. They need the platform image.
"""

from datetime import UTC, datetime

import pytest

pytest.importorskip("openg2p_registry_core")

from openg2p_registry_farmer_extension.openg2p_farmer.register_domain import (
    models as native,
)
from openg2p_registry_farmer_extension.register_domain import models as oan
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, configure_mappers


@compiles(JSONB, "sqlite")
def _jsonb(type_, compiler, **kw):
    return "JSON"


@compiles(UUID, "sqlite")
def _uuid(type_, compiler, **kw):
    return "CHAR(36)"


@compiles(ARRAY, "sqlite")
def _array(type_, compiler, **kw):
    return "JSON"


@pytest.fixture()
def session():
    configure_mappers()
    engine = create_engine("sqlite://")
    classes = [native.G2PRegisterFarmer, native.G2PRegisterLand, native.G2PRegisterCrop,
               native.G2PRegisterLivestock, native.G2PRegisterMembershipDetails,
               native.G2PRegisterFarmInputs, native.G2PIntakeFormLand]
    for cls in classes:
        cls.__table__.create(engine, checkfirst=True)
    with Session(engine) as db:
        yield db


def flushed(db, row):
    # the audit columns are filled by the service in a real save
    for column in ("created_by", "created_at", "last_approved_at", "last_approved_by"):
        if column in row.__table__.c and getattr(row, column) is None:
            setattr(row, column, datetime.now(UTC) if column.endswith("_at") else "tester")
    db.add(row)
    db.flush()
    db.refresh(row)
    return row.record_name


def test_native_rows_store_the_readable_name(session):
    assert flushed(session, native.G2PRegisterFarmer(first_name="Berhanu", middle_name="Abebe", last_name="Assefa")) \
        == "Berhanu Abebe Assefa"
    assert flushed(session, native.G2PRegisterLand(land_size=1.25, unit="HECTARE", current_land_use="GRAZING")) \
        == "1.25 Hectare, Grazing"
    assert flushed(session, native.G2PRegisterCrop(commodity="CROP_TEFF", season="SEASON_MEHER")) == "Teff, Meher"
    assert flushed(session, native.G2PRegisterLivestock(livestock_type="LSTK_CATTLE", breed="BREED_LOCAL")) \
        == "Cattle (Local)"
    assert flushed(session, native.G2PRegisterMembershipDetails(primary_cooperative_name="Tsehay Primary Cooperative")) \
        == "Tsehay Primary Cooperative"
    assert flushed(session, native.G2PRegisterFarmInputs(fertilizer_use=True)) == "Farm inputs (fertilizer)"


def test_an_update_renames_the_row(session):
    land = native.G2PRegisterLand(land_size=1, unit="HECTARE", current_land_use="GRAZING")
    assert flushed(session, land) == "1 Hectare, Grazing"
    land.land_size = 2
    session.flush()
    session.refresh(land)
    assert land.record_name == "2 Hectare, Grazing"


def test_oan_farmer_subclass_stores_all_three_names(session):
    assert flushed(session, oan.G2PRegisterFarmer(first_name="A", middle_name="B", last_name="C")) == "A B C"


def test_a_row_naming_nothing_keeps_the_platforms_name(session):
    assert flushed(session, native.G2PRegisterLand()) == "Land"


def test_a_flushed_intake_form_keeps_its_application_reference(session):
    form = native.G2PIntakeFormLand(land_size=3, unit="HECTARE", application_reference="APP-1")
    assert flushed(session, form) == "3 Hectare APP-1"
