"""Register the core services the platform celery worker leaves out.

``openg2p_registry_celery_worker.app.Initializer`` registers a short list of
services. On openg2p-registry-* 1.1.1 that list gained
``G2PIntakeFormDataService`` without gaining what it depends on, so an ODK or
partner ingest reaching the intake step dies on whichever dependency it touches
first:

    'NoneType' object has no attribute 'validate_records'
        -> G2PAttributeValueValidator, from intake_form_data_service.py:148
    'NoneType' object has no attribute 'get_intake_form_documents_with_session'
        -> G2PDocumentService

26 core services were unregistered in far, so fixing them one by one is a
losing game; this registers whatever is missing, which is what the core app's
own Initializer does for the API processes. The worker then holds the same
component set as staff-api rather than a subset of it.

1.1.0 workers (live, crop) do not register the intake service at all and so
never make these calls -- which is the only reason those environments look
healthy. There is nothing to fix in their configuration.

Wired from this package's ``__init__``, which the worker imports at startup via
``REGISTRY_EXTENSION_MODULE``, and run on celery's ``celeryd_init`` signal so it
happens after the platform Initializer has built config and the DB engine, and
before any task is consumed. Registration is additive: a service the platform
already registered is left alone, so this is inert once upstream fills the gap.
"""

import importlib
import inspect
import logging
import pkgutil

_logger = logging.getLogger(__name__)


def register_missing_core_services() -> list[str]:
    """Instantiate every unregistered BaseService in the core services package.

    Returns the names registered. Never raises: a worker that cannot start is
    worse than one missing a service it may not use.
    """
    registered: list[str] = []
    failed: list[str] = []

    try:
        from openg2p_fastapi_common.service import BaseService

        import openg2p_registry_core.services as services_pkg
    except Exception:
        _logger.exception("could not import the core services package")
        return registered

    for module_info in pkgutil.iter_modules(services_pkg.__path__):
        module_name = f"{services_pkg.__name__}.{module_info.name}"
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            # A module that will not import is not ours to repair here.
            _logger.debug("skipped %s (%s)", module_name, exc)
            continue

        for _, cls in inspect.getmembers(module, inspect.isclass):
            # Only classes this module defines, so a name re-exported across
            # modules is not instantiated more than once.
            if cls.__module__ != module.__name__:
                continue
            if not issubclass(cls, BaseService) or cls is BaseService:
                continue
            try:
                if cls.get_component() is not None:
                    continue
                cls()
                registered.append(cls.__name__)
            except Exception as exc:
                failed.append(f"{cls.__name__}: {exc}")

    if registered:
        _logger.warning(
            "registered %d core services the celery worker did not: %s",
            len(registered),
            ", ".join(sorted(registered)),
        )
    if failed:
        _logger.warning("could not register: %s", "; ".join(sorted(failed)))

    return registered


def install() -> None:
    """Run the registration when celery starts, if this is a celery process.

    The extension ships in the staff-api and partner-api images too, where
    celery is not installed and those processes register the full core set
    themselves. Absent celery this is a no-op.
    """
    try:
        from celery.signals import celeryd_init
    except Exception:
        return

    @celeryd_init.connect(weak=False)
    def _on_celeryd_init(**_kwargs):
        register_missing_core_services()
