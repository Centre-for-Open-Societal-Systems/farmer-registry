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
