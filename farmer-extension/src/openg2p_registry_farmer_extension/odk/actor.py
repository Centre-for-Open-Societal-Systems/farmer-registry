"""The ODK collector as an ingested intake's creator.

The platform creates every ingested intake as "system". For an ODK submission
the creator shown to staff is the collector named on the form (or, failing
that, Central's uploading account): a display and audit name, never a Registry
login or an approval identity. The authenticated partner stays the source.

The worker task knows which ingest it is processing; the intake service does
not. Celery's task_prerun signal records the ingest id for the task, and the
intake service reads it when the platform creates the submission.
"""
import contextvars
import logging

from . import ODK_DATA_MODEL

_logger = logging.getLogger(__name__)
INGEST_TASK = "ingest_data_worker"
PLATFORM_ACTOR = "system"

_ingest_id = contextvars.ContextVar("oan_odk_ingest_id", default=None)


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def collector(classified, enriched) -> str:
    """The collector for an ODK ingest, as farmer_transform.j2 reads it."""
    if classified is None or classified.data_model_id != ODK_DATA_MODEL or enriched is None:
        return PLATFORM_ACTOR
    data = enriched.enriched_data_json
    if not isinstance(data, dict):
        return PLATFORM_ACTOR
    # The enricher returns the submission itself; accept the connector's
    # payload envelope too, as the transform does.
    if isinstance(data.get("payload"), dict):
        data = data["payload"]
    survey = data.get("survey_metadata") if isinstance(data.get("survey_metadata"), dict) else {}
    system = data.get("__system") if isinstance(data.get("__system"), dict) else {}
    # The named collector first: Central's account may be a shared device.
    return _text(survey.get("enumerator_name")) or _text(system.get("submitterName")) or PLATFORM_ACTOR


def ingest_active() -> bool:
    """True while the worker is processing an ingest (it saves and finalizes
    without a person)."""
    return _ingest_id.get() is not None


async def ingest_actor(session, created_by):
    """The creator to record for a submission the worker is creating now."""
    ingest_id = _ingest_id.get()
    if created_by != PLATFORM_ACTOR or not ingest_id:
        return created_by
    from openg2p_registry_core.models import (
        IncomingClassifiedData,
        IncomingEnrichedTransformedData,
    )

    classified = await session.get(IncomingClassifiedData, ingest_id)
    enriched = await session.get(IncomingEnrichedTransformedData, ingest_id)
    return collector(classified, enriched)


def _record_ingest(sender=None, args=None, kwargs=None, **_):
    if getattr(sender, "name", None) != INGEST_TASK:
        return
    ingest_id = (kwargs or {}).get("ingest_id") or (args[0] if args else None)
    _ingest_id.set(ingest_id if isinstance(ingest_id, str) else None)


def _forget_ingest(sender=None, **_):
    if getattr(sender, "name", None) == INGEST_TASK:
        _ingest_id.set(None)


def install() -> None:
    """Listen for the ingest task, in the Celery worker only."""
    try:
        from celery.signals import task_postrun, task_prerun
    except ImportError:  # the staff and partner APIs have no Celery
        return
    task_prerun.connect(_record_ingest, weak=False)
    task_postrun.connect(_forget_ingest, weak=False)
