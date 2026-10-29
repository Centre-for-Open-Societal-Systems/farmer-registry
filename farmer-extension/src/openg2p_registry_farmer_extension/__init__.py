__version__ = "1.0.3+oan.1"
__variant__ = "farmer"

# OpenG2P's Farmer extension 1.0.3 is kept verbatim in ``openg2p_farmer``; this
# package is that extension with the OpenAgriNet layer on top. The modules here
# re-export ``openg2p_farmer`` and redefine the classes OAN extends under the
# same names, so the platform, which resolves domain classes by name on these
# modules, gets the OAN versions.
#
# The platform selects this package through REGISTRY_EXTENSION_MODULE and publishes
# it as ``openg2p_registry_extensions`` by assigning the package object in
# sys.modules. That aliases the package only. An import of an alias-name
# submodule such as ``openg2p_registry_extensions.register_domain.models`` finds
# no sys.modules entry, so Python executes the module file a second time and the
# mapped classes declare their tables twice on the shared MetaData ("Table
# 'g2p_register_farmers' is already defined for this MetaData instance"). The
# platform's ingestion classifier imports the models by the alias name inside the
# celery worker, which had loaded them under this real name at startup.
#
# The finder below resolves every alias-name submodule to the module already
# loaded (or loaded on demand) under this package's real name, so both names
# share one module object. It only acts while the alias points at this package.
import sys as _sys
from importlib import import_module as _import_module
from importlib.abc import Loader as _Loader
from importlib.abc import MetaPathFinder as _MetaPathFinder
from importlib.machinery import ModuleSpec as _ModuleSpec

PLATFORM_ALIAS = "openg2p_registry_extensions"
_REAL_NAME = __name__


class _SharedModuleLoader(_Loader):
    """Hands importlib the module object already loaded under the real name."""

    def __init__(self, module):
        self._module = module
        self._spec = module.__spec__

    def create_module(self, spec):
        return self._module

    def exec_module(self, module):
        # importlib stamps the alias spec onto the shared module; keep its own.
        module.__spec__ = self._spec


class _PlatformAliasFinder(_MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(PLATFORM_ALIAS + "."):
            return None
        if _sys.modules.get(PLATFORM_ALIAS) is not _sys.modules.get(_REAL_NAME):
            return None
        module = _import_module(_REAL_NAME + fullname[len(PLATFORM_ALIAS):])
        spec = _ModuleSpec(fullname, _SharedModuleLoader(module), origin=getattr(module, "__file__", None))
        if hasattr(module, "__path__"):
            spec.submodule_search_locations = list(module.__path__)
        return spec


if not any(isinstance(finder, _PlatformAliasFinder) for finder in _sys.meta_path):
    _sys.meta_path.insert(0, _PlatformAliasFinder())
