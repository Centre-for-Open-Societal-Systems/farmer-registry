"""Offline boot check: load an image's platform entry point as the image starts it.

The platform selects the extension with REGISTRY_EXTENSION_MODULE and publishes it
as openg2p_registry_extensions. The check confirms that the Farmer extension is
the one selected, that the platform's alias names resolve to the modules loaded
under the real name (one module object, so mapped tables are declared once), and
that the OAN classes are the ones the platform resolves by name.
Run inside an image:  python /repo/ci/validation/check_image_boot.py <role>
"""
import importlib
import json
import os
import sys

ENTRY_POINTS = {
    "staff-api": "openg2p_registry_staff_api.main",
    "partner-api": "openg2p_registry_partner_api.main",
    "celery-worker": "openg2p_registry_celery_worker.main",
    "celery-beat": "openg2p_registry_celery_beat.main",
}
PACKAGE = "openg2p_registry_farmer_extension"
SHARED = ("app", "config", "register_domain.models", "register_domain.schemas", "register_domain.services",
          "register_domain.id_generator", "ingestion_pipeline.enricher_services", "score_compute.services")

role = sys.argv[1]
# The queues the celery entry points read at import, as check_worker_extensions.py sets them.
os.environ.setdefault("REGISTRY_CELERY_WORKERS_WORKER_QUEUE", "owned-oan-boot-probe")
os.environ.setdefault("REGISTRY_CELERY_BEAT_WORKER_QUEUE", "owned-oan-boot-probe")
importlib.import_module(ENTRY_POINTS[role])
alias = sys.modules["openg2p_registry_extensions"]
assert alias.__name__ == PACKAGE, alias.__name__
for name in SHARED:
    shared = importlib.import_module("openg2p_registry_extensions." + name)
    assert shared is importlib.import_module(PACKAGE + "." + name), name
models = importlib.import_module("openg2p_registry_extensions.register_domain.models")
for cls in ("G2PRegisterFarmer", "G2PIntakeFormFarmer", "G2PRegisterFarmerPhone"):
    assert getattr(models, cls).__module__.startswith(PACKAGE + ".register_domain.models"), cls
openg2p_farmer = sys.modules[PACKAGE + ".openg2p_farmer"]
print(json.dumps({"image_boot": "PASS", "role": role, "extension": PACKAGE,
                  "version": alias.__version__, "openg2p_farmer_version": openg2p_farmer.__version__}))
