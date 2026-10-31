"""The Fayda verification is core's registrant authentication on the record:
OAN only carries core's outcome columns and the pinned platform's missing name."""
from datetime import datetime

from openg2p_registry_core.models import G2PRegisterAuthentication
from openg2p_registry_core.services import g2p_registrant_authentication_service as core_service
from openg2p_registry_farmer_extension.openg2p_farmer.register_domain import models as native
from openg2p_registry_farmer_extension.register_domain import models as oan
from openg2p_registry_farmer_extension.register_domain import schemas
from openg2p_registry_farmer_extension.register_domain.services.registrant_auth_compat import (
    install_registrant_auth_compat,
)

STAMPS = ("last_authentication_status", "last_authenticated_at", "authentication_expiry_at", "last_authentication_id")


def test_farmer_model_carries_core_authentication_mixin_on_the_native_table():
    assert issubclass(oan.G2PRegisterFarmer, G2PRegisterAuthentication)
    assert oan.G2PRegisterFarmer.__table__ is native.G2PRegisterFarmer.__table__
    for name in STAMPS + ("authentication_expiry_notified", "authentication_token"):
        assert name in oan.G2PRegisterFarmer.__table__.c, name
    # The intake form has no outcome: verification is of the approved record.
    assert "last_authenticated_at" not in oan.G2PIntakeFormFarmer.__table__.c
    # The OAN-only stamps of the retired popup are gone.
    for name in ("identity_verification_id", "last_authenticated_on", "authentication_expiry_date"):
        assert name not in oan.G2PRegisterFarmer.__table__.c, name


def test_register_schema_exposes_the_outcome_but_not_the_token():
    fields = schemas.G2PRegisterSchemaFarmer.model_fields
    for name in STAMPS:
        assert name in fields, name
    assert fields["last_authenticated_at"].annotation == (datetime | None)
    assert "authentication_token" not in fields
    assert "last_authenticated_at" not in schemas.G2PIntakeFormSchemaFarmer.model_fields


def test_compat_gives_core_the_session_maker_name_once():
    install_registrant_auth_compat()
    from openg2p_fastapi_common.context import get_async_session_maker

    assert core_service.get_async_session_maker is get_async_session_maker
    install_registrant_auth_compat()
    assert core_service.get_async_session_maker is get_async_session_maker


def test_add_oan_columns_ddl_gives_existing_rows_a_default():
    from openg2p_registry_farmer_extension.app import column_ddl
    from sqlalchemy.dialects import postgresql

    table = oan.G2PRegisterFarmer.__table__
    assert column_ddl(table.c.authentication_expiry_notified, postgresql.dialect()) == "BOOLEAN NOT NULL DEFAULT false"
    assert column_ddl(table.c.last_authenticated_at, postgresql.dialect()) == "TIMESTAMP WITHOUT TIME ZONE"
