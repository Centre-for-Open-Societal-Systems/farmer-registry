"""The platform patches the partner ingestion path needs still apply.

Partner (ODK connector) submissions reach staff only if

* the celery worker creates the services the draft-intake save reaches through
  get_component(), and the fastapi-cache backend -- the pinned worker's
  Initializer creates neither, so every ingest failed in ingest_data_worker;
* the Partner API can encode its response for a data model without a response
  template -- the pinned helper dumped the envelope with its datetime intact,
  so every ingest answered 500 and the connector re-sent it on each poll;
* the worker finalizes with a service token, so the AWE approval workflow
  starts as it does for a staff Submit -- without one it sat FINAL with no
  task for any approver.

The fixtures are the pinned files, copied from the images; running the
patcher on them fails loudly if the platform moved.
"""

import pathlib
import runpy
import shutil

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
PATCH_SCRIPT = REPO / "docker" / "patches" / "patch_platform.py"
FIXTURES = REPO / "test" / "fixtures"

WORKER_APP = pathlib.Path("openg2p_registry_celery_worker/app.py")
INGEST_WORKER = pathlib.Path("openg2p_registry_celery_worker/tasks/ingest_data_worker.py")
RESPONSE_HELPER = pathlib.Path(
    "openg2p_registry_partner_api/ingestion/helpers/request_response_helper.py"
)


@pytest.fixture
def patched(tmp_path, monkeypatch, capsys):
    for relative, fixture in (
        (WORKER_APP, "celery_worker_app.py"),
        (INGEST_WORKER, "celery_ingest_data_worker.py"),
        (RESPONSE_HELPER, "partner_api_request_response_helper.py"),
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True)
        shutil.copyfile(FIXTURES / fixture, target)

    monkeypatch.setenv("PATCH_PLATFORM_SITE_PACKAGES", str(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(PATCH_SCRIPT), run_name="__main__")
    out = capsys.readouterr()
    assert exit_info.value.code == 0, out.err
    assert "applied to app.py" in out.out
    assert "applied to request_response_helper.py" in out.out
    assert "applied to ingest_data_worker.py" in out.out
    return (
        (tmp_path / WORKER_APP).read_text(),
        (tmp_path / RESPONSE_HELPER).read_text(),
        (tmp_path / INGEST_WORKER).read_text(),
    )


def test_worker_initializer_creates_what_the_intake_save_needs(patched):
    worker_app, _, _ = patched
    compile(worker_app, "app.py", "exec")
    initializer = worker_app[worker_app.index("class Initializer"):worker_app.index("celery_app = Celery(")]
    for created in (
        "init_cache()",
        "AweHelper()",
        "G2PAttributeValueValidator()",
        "G2PAweIntegrationService()",
        "G2PAwePolicyConfigurationService()",
        "G2PCompletionScoreService()",
        "G2PDocumentService()",
        "G2PRegisterHistoryService()",
        "G2PScoreComputeService()",
        "G2PRegisterVerificationService()",
    ):
        assert created in initializer, created


def test_untemplated_response_is_dumped_as_json(patched):
    _, helper, _ = patched
    compile(helper, "request_response_helper.py", "exec")
    assert 'return JSONResponse(content=response.model_dump(mode="json"))' in helper
    assert "return JSONResponse(content=response.model_dump())" not in helper


def test_finalize_starts_the_workflow_with_a_service_token(patched):
    _, _, worker = patched
    compile(worker, "ingest_data_worker.py", "exec")
    finalize = worker[worker.index("async def _finalize_submission_async"):]
    assert "bearer_token=await _awe_service_token()," in finalize
    for setting in ("AWE_TOKEN_URL", "AWE_CLIENT_ID", "AWE_CLIENT_SECRET"):
        assert f'"REGISTRY_CELERY_WORKERS_{setting}"' in finalize


def test_rerun_is_a_no_op(patched, tmp_path, monkeypatch, capsys):
    """Every stage runs the whole script; a second run must not fail or re-apply."""
    monkeypatch.setenv("PATCH_PLATFORM_SITE_PACKAGES", str(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(PATCH_SCRIPT), run_name="__main__")
    out = capsys.readouterr()
    assert exit_info.value.code == 0, out.err
    assert "0 patch(es) applied" in out.out
