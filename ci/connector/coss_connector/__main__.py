"""Register extensions in the same process as upstream API/Celery workers."""
import runpy
import sys

from . import odk_media  # noqa: F401
from . import utc_timestamps  # noqa: F401
from .celery_config import configure
from .signing import install as install_signing
from openg2p_connector_service.worker import celery_app

# The API's Run Now, beat and workers must all use the same isolated queue.
configure(celery_app)
install_signing()

role, *extra = sys.argv[1:] or ["api"]
if role == "api":
    sys.argv = ["openg2p_connector_service.main", *extra]
    runpy.run_module("openg2p_connector_service.main", run_name="__main__")
elif role in ("worker", "beat"):
    from celery.__main__ import main
    sys.argv = ["celery", "-A", "openg2p_connector_service.worker.celery_app", role, "--loglevel=info", *extra]
    main()
elif role == "consumer":
    sys.argv = ["openg2p_connector_service.consumer_supervisor", *extra]
    runpy.run_module("openg2p_connector_service.consumer_supervisor", run_name="__main__")
else:
    raise SystemExit("Expected api, worker, beat or consumer")
