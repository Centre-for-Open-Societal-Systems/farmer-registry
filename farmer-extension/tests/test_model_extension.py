"""OAN models extend native models without reassigning platform methods."""
from openg2p_registry_farmer_extension.openg2p_farmer.register_domain import models as native
from openg2p_registry_farmer_extension.register_domain import models as oan


def test_discovered_models_use_oan_subclasses_and_preserve_native_methods():
    for name in ('G2PRegisterFarmer','G2PIntakeFormFarmer'):
        upstream, extension = getattr(native,name), getattr(oan,name)
        assert issubclass(extension,upstream) and extension is not upstream
        assert extension.__table__ is upstream.__table__
        assert upstream.get_search_text_fields.__module__.startswith('openg2p_registry_farmer_extension.openg2p_farmer')
        assert extension.get_search_text_fields.__module__.startswith('openg2p_registry_farmer_extension')
        assert 'income_sources' in extension.__table__.c


def test_native_farmer_instances_carry_the_authentication_columns():
    """Farmer-extension code loads farmers through its own class; to_dict must not fail."""
    from openg2p_registry_core.models import G2PRegisterAuthentication
    assert issubclass(oan.G2PRegisterFarmer, G2PRegisterAuthentication)
    assert not issubclass(native.G2PRegisterFarmer, G2PRegisterAuthentication)
    for name in ('last_authentication_id', 'last_authenticated_at', 'authentication_expiry_at', 'authentication_token'):
        assert name in native.G2PRegisterFarmer.__table__.c
        assert name in native.G2PRegisterFarmer.__mapper__.c
    row = native.G2PRegisterFarmer()
    data = row.to_dict()
    assert data['last_authentication_id'] is None
    assert set(oan.G2PRegisterFarmer().to_dict()) == set(data)


def test_oan_subclasses_fill_search_text_and_record_name_like_native_rows():
    """Core's listeners do not propagate to a subclass on a native table, so the
    register list (search_text ILIKE) would never show a farmer saved through it."""
    from sqlalchemy import event

    for name in ('G2PRegisterFarmer', 'G2PIntakeFormFarmer'):
        cls = getattr(oan, name)
        for event_name in ('before_insert', 'before_update'):
            assert event.contains(cls, event_name, oan._populate_derived_columns)
        row = cls(functional_record_id='FR-123456789012', foundational_id='502628318720',
                  first_name='Berhanu', middle_name='Abebe', last_name='Kebede')
        oan._populate_derived_columns(None, None, row)
        for value in ('FR-123456789012', '502628318720', 'Berhanu', 'Abebe', 'Kebede'):
            assert value in row.search_text
        assert row.record_name == 'Berhanu Abebe Kebede'


def test_registering_the_listeners_again_adds_nothing():
    dispatch = oan.G2PRegisterFarmer.__mapper__.dispatch.before_insert
    before = len(list(dispatch))
    oan._listen_like_core(oan.G2PRegisterFarmer)
    assert len(list(dispatch)) == before


def test_child_rows_are_named_from_their_values_after_core_names_them():
    """Core joins every class's name fields, so the readable name is set after it."""
    row = native.G2PRegisterLand(land_size=1.25, unit='HECTARE', current_land_use='GRAZING')
    oan._set_readable_record_name(row, 'Land')
    assert row.record_name == '1.25 Hectare, Grazing'
    for mnemonic in oan.READABLE_NAME_REGISTERS:
        for prefix in ('G2PRegister', 'G2PIntakeForm'):
            assert getattr(native, f'{prefix}{mnemonic}').__mapper__.dispatch.before_insert
