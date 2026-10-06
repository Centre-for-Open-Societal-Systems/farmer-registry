__version__ = "1.0.3"
__variant__ = "farmer"

# The celery worker imports this package at startup (REGISTRY_EXTENSION_MODULE),
# which is the only hook farmer code has into that process: CELERY_APP is set by
# the openg2p-registry subchart, so the image cannot point it elsewhere. This
# only arms a celery signal; see the module for what it repairs and why.
try:
    from . import celery_service_registration as _celery_service_registration

    _celery_service_registration.install()
except Exception:  # never block importing the extension
    pass
