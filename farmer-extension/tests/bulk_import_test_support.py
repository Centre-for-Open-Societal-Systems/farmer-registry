"""Load pure bulk modules without initializing the platform application."""
import importlib
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).parents[1] / "src" / "openg2p_registry_farmer_extension"
PREFIX = "farmer_bulk_test"
for suffix, path in [("", ROOT), (".register_domain", ROOT / "register_domain"),
                     (".register_domain.services", ROOT / "register_domain" / "services")]:
    name = PREFIX + suffix
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module

fi = importlib.import_module(PREFIX + ".bulk_import.farmer_import")
service = importlib.import_module(PREFIX + ".bulk_import.service")
