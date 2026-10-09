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
import re
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
    for setting in ("AWE_TOKEN_URL", "AWE_CLIENT_ID", "AWE_CLIENT_SECRET", "AWE_TOKEN_ISSUER_BASE_URL"):
        assert f'"REGISTRY_CELERY_WORKERS_{setting}"' in finalize


def test_rerun_is_a_no_op(patched, tmp_path, monkeypatch, capsys):
    """Every stage runs the whole script; a second run must not fail or re-apply."""
    monkeypatch.setenv("PATCH_PLATFORM_SITE_PACKAGES", str(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(PATCH_SCRIPT), run_name="__main__")
    out = capsys.readouterr()
    assert exit_info.value.code == 0, out.err
    assert "0 patch(es) applied" in out.out


def _log_helpers(worker_source, monkeypatch):
    """Run the patched worker's two log helpers against a recording log_event."""
    import sys
    import types

    events = []
    log_module = types.ModuleType("openg2p_registry_farmer_extension.ingest_log")
    log_module.log_event = lambda stage, event, severity="INFO", **fields: events.append(
        {"stage": stage, "event": event, "severity": severity, **fields}
    )
    package = types.ModuleType("openg2p_registry_farmer_extension")
    package.ingest_log = log_module
    monkeypatch.setitem(sys.modules, "openg2p_registry_farmer_extension", package)
    monkeypatch.setitem(sys.modules, "openg2p_registry_farmer_extension.ingest_log", log_module)

    start = worker_source.index("def _logged_ingest_error")
    end = worker_source.index("async def _process_ingestion_async")
    namespace = {
        "ProcessStatusEnum": types.SimpleNamespace(
            FAILED=types.SimpleNamespace(value="FAILED"),
            PENDING=types.SimpleNamespace(value="PENDING"),
        ),
        "_config": types.SimpleNamespace(worker_max_attempts=5),
    }
    exec(worker_source[start:end], namespace)
    return namespace, events


def _row(status, attempts):
    import types

    return types.SimpleNamespace(
        ingest_id="ing-1", ingestion_status=status, ingestion_number_of_attempts=attempts,
        intake_form_id="form", register_id="reg", partner_id="farmer-partner",
        intake_form_submission_id="sub-1",
    )


def test_failed_ingest_attempts_are_logged(patched, monkeypatch):
    _, _, worker = patched
    compile(worker, "ingest_data_worker.py", "exec")
    assert "ingestion_latest_error_code = _logged_ingest_error(incoming_classified_data, error_message)" in worker
    assert "ingestion_latest_error_code = _logged_ingest_success(incoming_classified_data)" in worker

    ns, events = _log_helpers(worker, monkeypatch)
    # Retry still pending: a warning that says the worker will try again.
    assert ns["_logged_ingest_error"](_row("PENDING", 2), "boom") == "boom"
    # Out of attempts: an error that says how to recover.
    assert ns["_logged_ingest_error"](_row("FAILED", 5), "gave up") == "gave up"
    retry, final = events
    assert (retry["event"], retry["severity"], retry["will_retry"]) == ("ingest_retry_scheduled", "WARNING", True)
    assert (final["event"], final["severity"], final["will_retry"]) == ("ingest_failed", "ERROR", False)
    assert final["ingest_id"] == "ing-1" and final["error"] == "gave up" and final["attempt"] == 5
    assert "PENDING" in final["next_step"]


def test_finished_ingest_is_logged(patched, monkeypatch):
    _, _, worker = patched
    ns, events = _log_helpers(worker, monkeypatch)
    assert ns["_logged_ingest_success"](_row("PROCESSED", 1)) is None
    assert events[0]["event"] == "ingest_succeeded"
    assert events[0]["submission_id"] == "sub-1"


def test_a_broken_log_never_changes_the_ingest_outcome(patched, monkeypatch):
    _, _, worker = patched
    ns, events = _log_helpers(worker, monkeypatch)
    import sys

    sys.modules["openg2p_registry_farmer_extension.ingest_log"].log_event = lambda *a, **k: 1 / 0
    assert ns["_logged_ingest_error"](_row("FAILED", 5), "msg") == "msg"
    assert ns["_logged_ingest_success"](_row("PROCESSED", 1)) is None


def test_worker_awe_settings_use_the_worker_prefix():
    """In the celery worker the platform reads its settings through the worker's
    own config class (prefix registry_celery_workers_), so AWE settings under
    REGISTRY_CORE_ are ignored there: AWE stays off and ingested intakes get no
    approval request, with no error anywhere."""
    for path in ("helm/openg2p-farmer-registry/values.yaml", "docker-compose.yml"):
        text = (REPO / path).read_text(encoding="utf-8")
        assert not re.search(r"^\s*REGISTRY_CORE_AWE_\w+:", text, re.M), path
        assert "REGISTRY_CELERY_WORKERS_AWE_ENABLED" in text, path


def test_worker_reaches_awe_in_cluster_with_the_public_issuer():
    """The ingress AWE URL needs a private CA the worker lacks, and a token from
    Keycloak's in-cluster address carries an issuer AWE rejects."""
    text = (REPO / "helm/openg2p-farmer-registry/values.yaml").read_text(encoding="utf-8")
    assert "REGISTRY_CELERY_WORKERS_AWE_BASE_URL: 'http://{{ tpl .Values.global.aweReleaseName $ }}-awe'" in text
    assert "REGISTRY_CELERY_WORKERS_AWE_TOKEN_ISSUER_BASE_URL: '{{ tpl .Values.global.keycloakBaseUrl $ }}'" in text


def test_service_token_request_presents_the_public_issuer(patched, monkeypatch):
    """Run the patched _awe_service_token against a fake httpx and check the
    token request goes to the in-cluster URL with the public host forwarded."""
    import ast
    import asyncio
    import sys
    import types

    _, _, worker = patched
    tree = ast.parse(worker)
    wanted = [n for n in tree.body
              if (isinstance(n, ast.AsyncFunctionDef) and n.name == "_awe_service_token")
              or (isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "_awe_token_cache")]
    namespace: dict = {}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "patched", "exec"), namespace)

    sent = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "tok", "expires_in": 300}

    class _Client:
        def __init__(self, **_kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, data=None):
            sent.update(url=url, headers=headers, data=data)
            return _Response()

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(AsyncClient=_Client))
    monkeypatch.setenv("REGISTRY_CELERY_WORKERS_AWE_TOKEN_URL",
                       "http://commons-keycloak.commons.svc.cluster.local:80/realms/staff/protocol/openid-connect/token")
    monkeypatch.setenv("REGISTRY_CELERY_WORKERS_AWE_CLIENT_ID", "farmer-registry-staff-portal")
    monkeypatch.setenv("REGISTRY_CELERY_WORKERS_AWE_CLIENT_SECRET", "s3cret")
    monkeypatch.setenv("REGISTRY_CELERY_WORKERS_AWE_TOKEN_ISSUER_BASE_URL", "https://keycloak.commons.openg2p.test")

    assert asyncio.run(namespace["_awe_service_token"]()) == "tok"
    assert sent["url"].startswith("http://commons-keycloak.commons.svc.cluster.local")
    assert sent["headers"] == {"X-Forwarded-Host": "keycloak.commons.openg2p.test",
                               "X-Forwarded-Proto": "https", "X-Forwarded-Port": "443"}
    assert sent["data"]["grant_type"] == "client_credentials"


def _patched_helpers(worker, names):
    import ast

    tree = ast.parse(worker)
    wanted = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    namespace: dict = {"_INGESTION_CREATED_BY": "system"}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "patched", "exec"), namespace)
    return namespace


def test_intake_is_created_by_the_odk_submitter(patched):
    """Partner intakes showed Created By: system; an ODK one shows who sent it."""
    import types

    _, _, worker = patched
    ns = _patched_helpers(worker, {"_odk_submitter", "_ingestion_created_by"})
    enriched = types.SimpleNamespace(enriched_data_json={"__system": {"submitterName": "Field_Officer_1"}})
    row = types.SimpleNamespace(_odk_submitter=ns["_odk_submitter"](enriched))
    assert ns["_ingestion_created_by"](row) == "Field_Officer_1 (ODK)"
    # Not ODK (no __system), or no submitter recorded: the platform default.
    assert ns["_odk_submitter"](types.SimpleNamespace(enriched_data_json={"reg_records": []})) is None
    assert ns["_ingestion_created_by"](types.SimpleNamespace()) == "system"
    # The worker uses it for the submission and for every section save.
    assert worker.count("created_by=_ingestion_created_by(incoming_classified_data)") == 2
    assert "created_by=_INGESTION_CREATED_BY" not in worker


def test_inline_files_are_uploaded_once_and_attached_to_their_section(patched, monkeypatch):
    """The header's Attached Documents lists a section's documents; the worker
    saved none, so ODK photos never appeared there or reached the record."""
    import asyncio
    import sys
    import types

    _, _, worker = patched
    ns = _patched_helpers(worker, {"_attach_embedded_files"})

    uploads = []

    async def upload_embedded_file(value, created_by, purpose="file"):
        uploads.append((value["name"], created_by, purpose))
        return f"doc-{len(uploads)}"

    class DocumentAttachment:
        def __init__(self, document_id, label):
            self.document_id, self.label = document_id, label

    utils = types.SimpleNamespace(
        is_embedded_file=lambda v: isinstance(v, dict) and v.get("__type") == "File",
        upload_embedded_file=upload_embedded_file,
    )
    monkeypatch.setitem(sys.modules, "openg2p_registry_farmer_extension.register_domain.services.domain_validation_utils", utils)
    monkeypatch.setitem(sys.modules, "openg2p_registry_core.schemas.file_payload", types.SimpleNamespace(DocumentAttachment=DocumentAttachment))

    photo = {"__type": "File", "name": "me.jpg", "type": "image/jpeg", "data": "aGk="}
    cert = {"__type": "File", "name": "deed.png", "type": "image/png", "data": "ZGVlZA=="}
    uploaded: dict = {}

    photo_section = types.SimpleNamespace(section_mnemonic="farmer_photo_section")
    incoming = [{"record_image_document_id": photo}]
    merged = [{"first_name": "Desta", "record_image_document_id": dict(photo)}]
    docs = asyncio.run(ns["_attach_embedded_files"](photo_section, incoming, merged, "Field_Officer_1 (ODK)", uploaded))
    assert [(d.document_id, d.label) for d in docs] == [("doc-1", "farmer_photo")]
    assert incoming[0]["record_image_document_id"] == merged[0]["record_image_document_id"] == "doc-1"

    land_section = types.SimpleNamespace(section_mnemonic="land_details")
    incoming = [{"land_id": "02", "certificate_storage_id": cert}, {"land_id": "03", "certificate_storage_id": None}]
    docs = asyncio.run(ns["_attach_embedded_files"](land_section, incoming, list(incoming), "Field_Officer_1 (ODK)", uploaded))
    assert [(d.document_id, d.label) for d in docs] == [("doc-2", "certificate_storage_id")]
    assert incoming[0]["certificate_storage_id"] == "doc-2"

    # A later section of the same register carrying the same photo does not upload it again.
    later = [{"record_image_document_id": dict(photo)}]
    asyncio.run(ns["_attach_embedded_files"](photo_section, later, later, "Field_Officer_1 (ODK)", uploaded))
    assert [u[0] for u in uploads] == ["me.jpg", "deed.png"]
    assert uploads[0][1:] == ("Field_Officer_1 (ODK)", "farmer_photo_section.record_image_document_id")

    assert "documents=section_documents or None," in worker
