"""Install the extension when the connector imports its ingestion service.

Runs from openg2p_registry_connector_extension.pth at interpreter start. Importing the
connector there could fail before its settings are readable, and site.py only prints a
failing .pth line, so the wrap waits for the module's own import instead.
"""

import importlib.abc
import importlib.machinery
import sys

TARGET = "openg2p_connector_service.services.ingestion_service"


class _Loader(importlib.abc.Loader):
    def __init__(self, loader):
        self._loader = loader

    def create_module(self, spec):
        return self._loader.create_module(spec)

    def exec_module(self, module):
        self._loader.exec_module(module)
        from .install import install

        install(module.IngestionService)


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name != TARGET:
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is not None and spec.loader is not None:
            spec.loader = _Loader(spec.loader)
        return spec


def register() -> None:
    if TARGET in sys.modules:
        from .install import install

        install(sys.modules[TARGET].IngestionService)
    elif not any(isinstance(f, _Finder) for f in sys.meta_path):
        sys.meta_path.insert(0, _Finder())
