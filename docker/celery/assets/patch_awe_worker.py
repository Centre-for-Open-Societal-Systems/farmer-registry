"""Supply an AWE service token at the pinned platform's ingestion finalizer."""
import importlib.util
from pathlib import Path

OLD = '''async def _finalize_submission_async(submission_id: str, session) -> None:
    await G2PIntakeFormDataService.get_component().finalize_submission_with_session(
        submission_id,
        session,
    )
'''
NEW = '''async def _finalize_submission_async(submission_id: str, session) -> None:
    from openg2p_registry_farmer_extension.awe_worker_token import service_token

    await G2PIntakeFormDataService.get_component().finalize_submission_with_session(
        submission_id,
        session,
        bearer_token=await service_token(),
    )
'''


def patch(path):
    source = path.read_text()
    if source.count(NEW) == 1 and OLD not in source:
        return
    if source.count(OLD) != 1:
        raise RuntimeError("Platform finalizer changed; review AWE worker integration")
    updated = source.replace(OLD, NEW, 1)
    compile(updated, str(path), "exec")
    path.write_text(updated)


if __name__ == "__main__":
    spec = importlib.util.find_spec("openg2p_registry_celery_worker")
    patch(Path(spec.origin).parent / "tasks/ingest_data_worker.py")
