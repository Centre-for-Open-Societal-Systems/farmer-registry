"""Register history loads change_request_source as the platform enum."""

from datetime import datetime

import pytest

pytest.importorskip("openg2p_registry_core")
from openg2p_registry_core.models import G2PRegisterHistory
from openg2p_registry_core.models.enum import ChangeRequestSourceEnum
from openg2p_registry_farmer_extension import history_change_request_source
from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import Session


class G2PRegisterHistoryHistorySourceProbe(G2PRegisterHistory):
    __tablename__ = "g2p_register_history_history_source_probe"


def _load(source):
    history_change_request_source.install()
    engine = create_engine("sqlite://")
    table = G2PRegisterHistoryHistorySourceProbe.__table__
    table.create(engine)
    samples = {str: "x", bool: False, int: 1, datetime: datetime(2026, 10, 29)}
    row = {column.name: samples.get(column.type.python_type, "x") for column in table.columns}
    row["change_request_source"] = source
    with Session(engine) as session:
        session.execute(insert(table).values(**row))
        return session.scalars(select(G2PRegisterHistoryHistorySourceProbe)).one()


def test_loaded_source_has_the_value_the_platform_reads():
    record = _load("INTAKE_FORM")
    assert record.change_request_source.value == "INTAKE_FORM"
    assert record.change_request_source == "INTAKE_FORM"


def test_loading_does_not_mark_the_record_changed():
    record = _load("PARTNER")
    assert record.change_request_source is ChangeRequestSourceEnum.PARTNER
    from sqlalchemy import inspect

    assert not inspect(record).modified


def test_unknown_source_is_left_as_stored():
    assert _load("SOMETHING_ELSE").change_request_source == "SOMETHING_ELSE"


def test_install_is_idempotent():
    history_change_request_source.install()
    history_change_request_source.install()
    from sqlalchemy import event

    assert event.contains(G2PRegisterHistory, "load", history_change_request_source._on_load)
