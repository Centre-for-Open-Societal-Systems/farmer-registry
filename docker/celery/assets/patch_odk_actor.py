"""Replace rc.544's hardcoded ingestion actor with the ODK collector name."""
import importlib.util
from pathlib import Path


INTAKE_REPLACEMENTS = (
    ("_INGESTION_CREATED_BY = \"system\"\n",
     "_INGESTION_CREATED_BY = \"system\"\n"
     "from openg2p_registry_farmer_extension.odk_actor import ingestion_created_by\n"),
    ("            submission_id, already_processed = await _prepare_submission_for_ingestion(\n",
     "            created_by = ingestion_created_by(incoming_classified_data, incoming_enriched_transformed_data)\n\n"
     "            submission_id, already_processed = await _prepare_submission_for_ingestion(\n"),
    ("await _create_submission_async(incoming_classified_data, session)",
     "await _create_submission_async(incoming_classified_data, session, created_by=created_by)"),
    ("                transformed_data,\n                session,\n",
     "                transformed_data,\n                session,\n                created_by=created_by,\n"),
    ("async def _create_submission_async(incoming_classified_data: IncomingClassifiedData, session) -> str:",
     "async def _create_submission_async(incoming_classified_data: IncomingClassifiedData, session, *, created_by: str = _INGESTION_CREATED_BY) -> str:"),
    ("    transformed_data: dict[str, list[dict]],\n    session,\n) -> None:",
     "    transformed_data: dict[str, list[dict]],\n    session,\n    *, created_by: str = _INGESTION_CREATED_BY,\n) -> None:"),
    ("created_by=_INGESTION_CREATED_BY,", "created_by=created_by,"),
)
CHANGE_REPLACEMENTS = (
    ("from ..app import celery_app\n",
     "from openg2p_registry_farmer_extension.odk_actor import ingestion_created_by\n\nfrom ..app import celery_app\n"),
    ('                    created_by="system",',
     '                    created_by=ingestion_created_by(classified, enriched),'),
)


def patch(path, replacements):
    source = path.read_text()
    marker = "from openg2p_registry_farmer_extension.odk_actor import ingestion_created_by"
    if marker in source:
        if all(source.count(new) == (3 if old == "created_by=_INGESTION_CREATED_BY," else 1)
               for old, new in replacements):
            return
        raise RuntimeError("Platform ODK actor patch is incomplete; review ingestion integration")
    updated = source
    for old, new in replacements:
        expected = 2 if old == "created_by=_INGESTION_CREATED_BY," else 1
        if updated.count(old) != expected:
            raise RuntimeError("Platform ingestion changed; review ODK actor integration")
        updated = updated.replace(old, new)
    compile(updated, str(path), "exec")
    path.write_text(updated)


if __name__ == "__main__":
    spec = importlib.util.find_spec("openg2p_registry_celery_worker")
    tasks = Path(spec.origin).parent / "tasks"
    patch(tasks / "ingest_data_worker.py", INTAKE_REPLACEMENTS)
    patch(tasks / "change_request_ingest_worker.py", CHANGE_REPLACEMENTS)
