"""OAN models extend native models without reassigning platform methods."""
from openg2p_registry_farmer_extension.register_domain import models as native
from openg2p_registry_oan_extension.register_domain import models as oan


def test_discovered_models_use_oan_subclasses_and_preserve_native_methods():
    for name in ('G2PRegisterFarmer','G2PIntakeFormFarmer'):
        upstream, extension = getattr(native,name), getattr(oan,name)
        assert issubclass(extension,upstream) and extension is not upstream
        assert extension.__table__ is upstream.__table__
        assert upstream.get_search_text_fields.__module__.startswith('openg2p_registry_farmer_extension')
        assert extension.get_search_text_fields.__module__.startswith('openg2p_registry_oan_extension')
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
