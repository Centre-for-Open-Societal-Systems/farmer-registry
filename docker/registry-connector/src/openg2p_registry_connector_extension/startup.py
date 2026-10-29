"""Install the extension when the connector imports the modules it extends.

Runs from openg2p_registry_connector_extension.pth at interpreter start. Importing the
connector there could fail before its settings are readable, and site.py only prints a
failing .pth line, so each wrap waits for its module's own import instead:

* ``...services.ingestion_service``: registry signature and WebSub content (``install``).
* ``...main``: admin-only API (``admin_auth``). ``python -m ...main`` runs that file as
  ``__main__``; uvicorn then imports ``openg2p_connector_service.main:app``, the app it
  serves, through this hook.
"""

import importlib.abc
import importlib.machinery
import sys


def _ingestion(module) -> None:
    from .install import install

    install(module.IngestionService)


def _api(module) -> None:
    from .admin_auth import install

    install(module.app)


TARGETS = {
    "openg2p_connector_service.services.ingestion_service": _ingestion,
    "openg2p_connector_service.main": _api,
}


class _Loader(importlib.abc.Loader):
    def __init__(self, loader, extend):
        self._loader, self._extend = loader, extend

    def create_module(self, spec):
        return self._loader.create_module(spec)

    def exec_module(self, module):
        self._loader.exec_module(module)
        self._extend(module)

    def get_code(self, fullname):  # runpy (python -m) reads the code through the loader
        return self._loader.get_code(fullname)


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        extend = TARGETS.get(name)
        if extend is None:
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is not None and spec.loader is not None:
            spec.loader = _Loader(spec.loader, extend)
        return spec


def register() -> None:
    for name, extend in TARGETS.items():
        if name in sys.modules:
            extend(sys.modules[name])
    if not any(isinstance(f, _Finder) for f in sys.meta_path):
        sys.meta_path.insert(0, _Finder())
