#!/usr/bin/env python3
"""Overlay fixes for the pinned registry-platform images.

Each entry patches a bug that the pinned platform ships: async/await mismatches
in openg2p_registry_core, and the IAM permission lookup in iam_core. Applied at
image build time to every stage that installs registry-core (staff-api,
partner-api, celery), because the same packages are present in all of them; a
patch whose file is absent from a stage is skipped.

Drop an entry here once the corresponding fix lands in the platform image the
RP_VERSION pin points at -- the script fails loudly if a patch stops matching,
so a stale entry surfaces on the next build rather than rotting silently.

PATCH_PLATFORM_SITE_PACKAGES overrides the target directory so the patches can
be exercised against a copy of the sources outside an image (test/).
"""

from __future__ import annotations

import os
import pathlib
import sys

SITE_PACKAGES = pathlib.Path(
    os.environ.get(
        "PATCH_PLATFORM_SITE_PACKAGES", "/usr/local/lib/python3.12/site-packages"
    )
)


class Patch:
    def __init__(self, relative_path: str, old: str, new: str, why: str):
        self.path = SITE_PACKAGES / relative_path
        self.old = old
        self.new = new
        self.why = why


PATCHES = [
    Patch(
        "openg2p_registry_core/services/intake_form_data_service.py",
        old="    def _build_intake_policy_condition(",
        new="    async def _build_intake_policy_condition(",
        why=(
            "Declared as a plain def but every call site awaits it. Here the "
            "method is the odd one out, so it becomes async."
        ),
    ),
    Patch(
        "openg2p_registry_core/services/g2p_register_service.py",
        old="policy_condition = await self._build_register_policy_condition(",
        new="policy_condition = self._build_register_policy_condition(",
        why=(
            "The mirror image of the patch above: _build_register_policy_condition "
            "is correctly a plain def and four of its five call sites treat it as "
            "one. Only get_record awaits it, so awaiting the returned condition "
            "(or the None it returns when no data policies apply) raised "
            "\"object NoneType can't be used in 'await' expression\" on every "
            "single-record read -- get_subject_record caught it and returned an "
            "error body with HTTP 200, so the staff portal showed an empty "
            "record rather than a failure. The await is removed rather than the "
            "method made async, which would break the other four call sites."
        ),
    ),
    Patch(
        "iam_core/user_auth/middleware/resolve_permissions.py",
        old='''    async def _fetch_permissions_for_roles(self, role_mnemonics: list[str]) -> set[str]:
        """Resolve role mnemonics to permission strings via the auth provider API."""
        auth_provider_api_url = (self._config.auth_provider_api_url or "").strip()
        if not auth_provider_api_url:
            raise ForbiddenError(message="Forbidden. auth_provider_api_url is not configured.")

        if not role_mnemonics:
            return set()

        endpoint = auth_provider_api_url.rstrip("/") + "/user-access/get_permissions_for_roles"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint,
                    json={"role_mnemonics": role_mnemonics},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ForbiddenError(message="Forbidden. Unable to fetch user permissions.") from exc

        response_data = response.json() or {}
        return set(response_data.get("permissions") or [])
''',
        new='''    async def _fetch_permissions_for_roles(
        self,
        role_mnemonics: list[str],
        principal: AuthPrincipal | None = None,
        client_id: str | None = None,
    ) -> set[str]:
        """Resolve the caller's permissions on THIS application via the auth provider API.

        Patched by farmer-registry (docker/patches/patch_platform.py): the platform
        asks IAM `get_permissions_for_roles` with bare role names, and IAM answers
        with the first active role of that name across EVERY registered application.
        On a cluster hosting several registries (farmer, livestock, cropsown, a stale
        `registry-staff-portal`) the roles share names, so a user's permissions
        silently come from whichever application's row sorts first -- and if that
        one carries older permission mnemonics, every endpoint answers 403. IAM's
        `get_application_permissions_for_user?application_mnemonic=<client_id>`
        resolves the same token's roles inside one application only, so that is
        what we call, and we keep only the entry for our own client.
        """
        auth_provider_api_url = (self._config.auth_provider_api_url or "").strip()
        if not auth_provider_api_url:
            raise ForbiddenError(message="Forbidden. auth_provider_api_url is not configured.")

        if not role_mnemonics:
            return set()

        if principal is None or not principal.credentials or not client_id:
            raise ForbiddenError(message="Forbidden. Unable to fetch user permissions.")

        endpoint = auth_provider_api_url.rstrip("/") + "/user-access/get_application_permissions_for_user"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    endpoint,
                    params={"application_mnemonic": client_id},
                    headers={"Authorization": f"Bearer {principal.credentials}"},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ForbiddenError(message="Forbidden. Unable to fetch user permissions.") from exc

        permissions: set[str] = set()
        for application in response.json() or []:
            if (application or {}).get("application_mnemonic") == client_id:
                permissions.update(application.get("permissions") or [])
        return permissions
''',
        why=(
            "IAM's get_permissions_for_roles matches roles by name across all "
            "registered applications, so same-named roles of another registry "
            "(or a stale one) decide this registry's permissions. Resolve them "
            "per application with get_application_permissions_for_user instead."
        ),
    ),
    Patch(
        "iam_core/user_auth/middleware/resolve_permissions.py",
        old="            user_permissions = await self._fetch_permissions_for_roles(user_roles)\n",
        new=(
            "            user_permissions = await self._fetch_permissions_for_roles(\n"
            "                user_roles, principal, client_id\n"
            "            )\n"
        ),
        why="Hand the caller's token and this service's client id to the scoped lookup above.",
    ),
    Patch(
        "openg2p_registry_celery_worker/app.py",
        # Anchored on the line after the insertion point too, so the new text
        # does not contain the old one and a re-run reports "already applied".
        # From registry-platform 1.2.2 the worker creates the attribute
        # validator, document, AWE and AWE policy services itself; these are the
        # ones it still leaves out.
        old="        G2PAttributeValueValidator()\n\n        # Factories",
        new=(
            "        G2PAttributeValueValidator()\n"
            "\n"
            "        # Created by the staff-api's Initializer but not by this one, while\n"
            "        # ingest_data_worker saves the draft intake through the same\n"
            "        # intake-form and domain services, which reach them by\n"
            "        # get_component() (None here) and the fastapi-cache decorator.\n"
            "        from openg2p_registry_core.cache import init_cache\n"
            "        from openg2p_registry_core.services.g2p_completion_score_service import G2PCompletionScoreService\n"
            "        from openg2p_registry_core.services.g2p_register_history_service import G2PRegisterHistoryService\n"
            "        from openg2p_registry_core.services.g2p_score_compute_service import G2PScoreComputeService\n"
            "        from openg2p_registry_core.services.g2p_verification_service import G2PRegisterVerificationService\n"
            "\n"
            "        init_cache()\n"
            "        G2PCompletionScoreService()\n"
            "        G2PRegisterHistoryService()\n"
            "        G2PScoreComputeService()\n"
            "        G2PRegisterVerificationService()\n"
            "\n"
            "        # Factories"
        ),
        why=(
            "The celery worker never creates the "
            "history, verification and score services, nor the "
            "fastapi-cache "
            "backend. Saving an ingested submission as a draft intake (the ODK "
            "and DCI paths) needs all of them, so every ingest failed with "
            "\"'NoneType' object has no attribute ...\" or \"You must call init "
            "first!\" and never reached staff."
        ),
    ),
    Patch(
        "openg2p_registry_celery_worker/tasks/ingest_data_worker.py",
        old=(
            "async def _finalize_submission_async(submission_id: str, session) -> None:\n"
            "    await G2PIntakeFormDataService.get_component().finalize_submission_with_session(\n"
            "        submission_id,\n"
            "        session,\n"
            "    )\n"
        ),
        new=(
            "async def _finalize_submission_async(submission_id: str, session) -> None:\n"
            "    await G2PIntakeFormDataService.get_component().finalize_submission_with_session(\n"
            "        submission_id,\n"
            "        session,\n"
            "        bearer_token=await _awe_service_token(),\n"
            "    )\n"
            "\n"
            "\n"
            "_awe_token_cache: dict = {}\n"
            "\n"
            "\n"
            "async def _awe_service_token() -> str | None:\n"
            '    """Token the intake\'s approval workflow is started with.\n'
            "\n"
            "    Finalizing starts the AWE workflow, and AWE needs a token of the realm.\n"
            "    A worker has no user's, so it takes a client-credentials token of\n"
            "    REGISTRY_CELERY_WORKERS_AWE_CLIENT_ID. With those settings unset this is\n"
            "    None and AWE, when enabled, refuses with AWE_BEARER_TOKEN_REQUIRED, which\n"
            "    marks the ingest FAILED with that reason.\n"
            '    """\n'
            "    import os\n"
            "    import time\n"
            "\n"
            "    import httpx\n"
            "\n"
            '    token_url = os.environ.get("REGISTRY_CELERY_WORKERS_AWE_TOKEN_URL")\n'
            '    client_id = os.environ.get("REGISTRY_CELERY_WORKERS_AWE_CLIENT_ID")\n'
            '    client_secret = os.environ.get("REGISTRY_CELERY_WORKERS_AWE_CLIENT_SECRET")\n'
            "    if not (token_url and client_id and client_secret):\n"
            "        return None\n"
            '    if _awe_token_cache.get("expires_at", 0) > time.time() + 30:\n'
            '        return _awe_token_cache["token"]\n'
            "    # The token URL is usually Keycloak's in-cluster address, and Keycloak\n"
            "    # stamps the issuer from the host it is called on, which AWE does not\n"
            "    # accept. REGISTRY_CELERY_WORKERS_AWE_TOKEN_ISSUER_BASE_URL (the public\n"
            "    # Keycloak base) is presented as X-Forwarded-* so the token carries the\n"
            "    # issuer AWE trusts, while the call itself stays in-cluster.\n"
            "    headers = {}\n"
            '    issuer_base = os.environ.get("REGISTRY_CELERY_WORKERS_AWE_TOKEN_ISSUER_BASE_URL")\n'
            "    if issuer_base:\n"
            "        from urllib.parse import urlsplit\n"
            "\n"
            "        public = urlsplit(issuer_base)\n"
            "        headers = {\n"
            '            "X-Forwarded-Host": public.hostname or "",\n'
            '            "X-Forwarded-Proto": public.scheme or "https",\n'
            '            "X-Forwarded-Port": str(public.port or (443 if public.scheme != "http" else 80)),\n'
            "        }\n"
            "    async with httpx.AsyncClient(timeout=30) as client:\n"
            "        response = await client.post(\n"
            "            token_url,\n"
            "            headers=headers,\n"
            "            data={\n"
            '                "grant_type": "client_credentials",\n'
            '                "client_id": client_id,\n'
            '                "client_secret": client_secret,\n'
            "            },\n"
            "        )\n"
            "        response.raise_for_status()\n"
            "        body = response.json()\n"
            '    _awe_token_cache["token"] = body["access_token"]\n'
            '    _awe_token_cache["expires_at"] = time.time() + int(body.get("expires_in", 60))\n'
            '    return body["access_token"]\n'
        ),
        why=(
            "The worker finalized ingested submissions without a token, so no AWE "
            "approval workflow started (or, with AWE enabled, finalize failed): the "
            "submission sat FINAL with no task for any approver. It now starts the "
            "workflow as a staff Submit does, with a service client's token."
        ),
    ),
    Patch(
        "openg2p_registry_celery_worker/tasks/ingest_data_worker.py",
        old="async def _process_ingestion_async(ingest_id: str) -> None:\n",
        new=(
            "def _logged_ingest_error(row, error_message):\n"
            '    """Write the failed ingest to the ODK ingestion log; returns the message."""\n'
            "    try:\n"
            "        from openg2p_registry_farmer_extension.ingest_log import log_event\n"
            "\n"
            "        final = row.ingestion_status == ProcessStatusEnum.FAILED.value\n"
            "        log_event(\n"
            '            "ingest", "ingest_failed" if final else "ingest_retry_scheduled",\n'
            '            "ERROR" if final else "WARNING",\n'
            "            ingest_id=row.ingest_id,\n"
            '            message_id=getattr(row, "message_id", None),\n'
            "            intake_form_id=row.intake_form_id,\n"
            "            register_id=row.register_id,\n"
            "            partner_id=row.partner_id,\n"
            "            attempt=row.ingestion_number_of_attempts,\n"
            "            max_attempts=_config.worker_max_attempts,\n"
            "            will_retry=not final,\n"
            "            error=error_message,\n"
            "            next_step=(\n"
            '                "gave up after the last attempt; fix the cause, then set "\n'
            '                "incoming_classified_data.ingestion_status back to PENDING"\n'
            "                if final else \"the worker retries this ingest\"\n"
            "            ),\n"
            "        )\n"
            "    except Exception:  # a log must never change the ingest outcome\n"
            "        pass\n"
            "    return error_message\n"
            "\n"
            "\n"
            "def _logged_ingest_success(row):\n"
            '    """Write the finished ingest to the ODK ingestion log; returns None."""\n'
            "    try:\n"
            "        from openg2p_registry_farmer_extension.ingest_log import log_event\n"
            "\n"
            "        log_event(\n"
            '            "ingest", "ingest_succeeded",\n'
            "            ingest_id=row.ingest_id,\n"
            '            message_id=getattr(row, "message_id", None),\n'
            "            submission_id=row.intake_form_submission_id,\n"
            "            intake_form_id=row.intake_form_id,\n"
            "            register_id=row.register_id,\n"
            "            attempt=row.ingestion_number_of_attempts,\n"
            "        )\n"
            "    except Exception:\n"
            "        pass\n"
            "    return None\n"
            "\n"
            "\n"
            "async def _process_ingestion_async(ingest_id: str, /) -> None:\n"
        ),
        why=(
            "The worker logs a failed ingest only as one ERROR line and keeps the "
            "reason in incoming_classified_data. Adds the helpers that write every "
            "attempt, retry and final failure to the ODK ingestion log."
        ),
    ),
    Patch(
        "openg2p_registry_celery_worker/tasks/ingest_data_worker.py",
        old="        incoming_classified_data.ingestion_latest_error_code = error_message\n",
        new=(
            "        incoming_classified_data.ingestion_latest_error_code = "
            "_logged_ingest_error(incoming_classified_data, error_message)\n"
        ),
        why="Logs each failed attempt (and whether the worker will retry) to the ODK ingestion log.",
    ),
    Patch(
        "openg2p_registry_celery_worker/tasks/ingest_data_worker.py",
        old="            incoming_classified_data.ingestion_latest_error_code = None\n",
        new=(
            "            incoming_classified_data.ingestion_latest_error_code = "
            "_logged_ingest_success(incoming_classified_data)\n"
        ),
        why="Logs a finished ingest, with the draft intake it created, to the ODK ingestion log.",
    ),
    Patch(
        "openg2p_registry_celery_worker/tasks/ingest_data_worker.py",
        # Anchored on the line after it, which the logging patch above puts
        # there, so a re-run finds the helpers in between and skips.
        old='_INGESTION_CREATED_BY = "system"\n\n\ndef _logged_ingest_error(',
        new=(
            '_INGESTION_CREATED_BY = "system"\n'
            "\n"
            "\n"
            "def _odk_submitter(incoming_enriched_transformed_data):\n"
            '    """The ODK Central user who sent the submission (__system.submitterName)."""\n'
            "    data = incoming_enriched_transformed_data.enriched_data_json\n"
            "    if isinstance(data, str):\n"
            "        try:\n"
            "            import json\n"
            "\n"
            "            data = json.loads(data)\n"
            "        except ValueError:\n"
            "            return None\n"
            "    for _ in range(4):\n"
            "        if not isinstance(data, dict):\n"
            "            return None\n"
            '        system = data.get("__system")\n'
            "        if isinstance(system, dict):\n"
            '            name = (system.get("submitterName") or "").strip()\n'
            "            return name or None\n"
            '        data = data.get("body") or data.get("message") or data.get("payload")\n'
            "    return None\n"
            "\n"
            "\n"
            "def _ingestion_created_by(incoming_classified_data):\n"
            '    """Who the intake shows as its creator: the ODK user, else the platform default."""\n'
            '    submitter = getattr(incoming_classified_data, "_odk_submitter", None)\n'
            '    return f"{submitter} (ODK)" if submitter else _INGESTION_CREATED_BY\n'
            "\n"
            "\n"
            "async def _attach_embedded_files(section, incoming_records, merged_records, created_by, uploaded):\n"
            '    """Upload the files a section\'s records carry inline and attach them to the section.\n'
            "\n"
            "    The connector sends ODK photos as {\"__type\": \"File\", ...}. Each one is\n"
            "    uploaded once (uploaded caches it for the whole submission), replaced by\n"
            "    its document id wherever the records hold it, and returned as the\n"
            "    section's documents, labelled as the staff UI labels its own uploads (the\n"
            "    field name, farmer_photo for the profile photo). The intake header lists\n"
            '    them under Attached Documents and approval carries them to the record."""\n'
            "    import hashlib\n"
            "\n"
            "    from openg2p_registry_core.schemas.file_payload import DocumentAttachment\n"
            "    from openg2p_registry_farmer_extension.register_domain.services.domain_validation_utils import (\n"
            "        is_embedded_file,\n"
            "        upload_embedded_file,\n"
            "    )\n"
            "\n"
            "    def key(value):\n"
            '        return (value.get("name"), hashlib.sha256((value.get("data") or "").encode()).hexdigest())\n'
            "\n"
            "    documents = []\n"
            "    for record in incoming_records:\n"
            "        for field, value in list(record.items()):\n"
            "            if not is_embedded_file(value):\n"
            "                continue\n"
            "            if key(value) not in uploaded:\n"
            "                uploaded[key(value)] = await upload_embedded_file(\n"
            '                    value, created_by, purpose=f"{section.section_mnemonic}.{field}"\n'
            "                )\n"
            '            label = "farmer_photo" if field == "record_image_document_id" else field\n'
            "            documents.append(DocumentAttachment(document_id=uploaded[key(value)], label=label))\n"
            "    for record in list(incoming_records) + list(merged_records):\n"
            "        for field, value in list(record.items()):\n"
            "            if is_embedded_file(value) and key(value) in uploaded:\n"
            "                record[field] = uploaded[key(value)]\n"
            "    return documents\n"
            "\n"
            "\n"
            "def _logged_ingest_error("
        ),
        why=(
            "Helpers for the two patches below: the ODK submitter as the intake's "
            "creator, and inline ODK files attached to their section."
        ),
    ),
    Patch(
        "openg2p_registry_celery_worker/tasks/ingest_data_worker.py",
        old=(
            "            if incoming_enriched_transformed_data is None:\n"
            "                raise ValueError(f\"Incoming transformed data not found for ingest_id '{ingest_id}'\")\n"
            "\n"
            "            ordered_sections"
        ),
        new=(
            "            if incoming_enriched_transformed_data is None:\n"
            "                raise ValueError(f\"Incoming transformed data not found for ingest_id '{ingest_id}'\")\n"
            "            incoming_classified_data._odk_submitter = _odk_submitter(incoming_enriched_transformed_data)\n"
            "\n"
            "            ordered_sections"
        ),
        why="Remembers who sent the ODK submission, for the intake's Created By.",
    ),
    Patch(
        "openg2p_registry_celery_worker/tasks/ingest_data_worker.py",
        old=(
            "        section_payloads=None,\n"
            "        created_by=_INGESTION_CREATED_BY,\n"
        ),
        new=(
            "        section_payloads=None,\n"
            "        created_by=_ingestion_created_by(incoming_classified_data),\n"
        ),
        why=(
            "Every partner intake showed Created By: system. An ODK submission now "
            "shows the ODK user who sent it."
        ),
    ),
    Patch(
        "openg2p_registry_celery_worker/tasks/ingest_data_worker.py",
        old=(
            "    ids_by_section_register_id: dict[str, list[str]] = {}\n"
            "\n"
            "    for section in ordered_sections:\n"
        ),
        new=(
            "    ids_by_section_register_id: dict[str, list[str]] = {}\n"
            "    uploaded_files: dict = {}\n"
            "\n"
            "    for section in ordered_sections:\n"
        ),
        why="A per-submission cache, so a file is uploaded once however many sections carry it.",
    ),
    Patch(
        "openg2p_registry_celery_worker/tasks/ingest_data_worker.py",
        old=(
            "        await G2PIntakeFormDataService().get_component().save_intake_form_submission_with_session(\n"
            "            submission_id=submission_id,\n"
            "            section_id=section.section_id,\n"
            "            section_payload=deepcopy(merged_records),\n"
            "            section_register_id=section.section_register_id,\n"
            "            form_id=incoming_classified_data.intake_form_id,\n"
            "            register_id=incoming_classified_data.register_id,\n"
            "            created_by=_INGESTION_CREATED_BY,\n"
            "            session=session,\n"
            "        )\n"
        ),
        new=(
            "        section_documents = await _attach_embedded_files(\n"
            "            section,\n"
            "            incoming_records,\n"
            "            merged_records,\n"
            "            _ingestion_created_by(incoming_classified_data),\n"
            "            uploaded_files,\n"
            "        )\n"
            "        await G2PIntakeFormDataService().get_component().save_intake_form_submission_with_session(\n"
            "            submission_id=submission_id,\n"
            "            section_id=section.section_id,\n"
            "            section_payload=deepcopy(merged_records),\n"
            "            section_register_id=section.section_register_id,\n"
            "            form_id=incoming_classified_data.intake_form_id,\n"
            "            register_id=incoming_classified_data.register_id,\n"
            "            created_by=_ingestion_created_by(incoming_classified_data),\n"
            "            documents=section_documents or None,\n"
            "            session=session,\n"
            "        )\n"
        ),
        why=(
            "The worker saved sections without documents, so an ODK photo or land "
            "certificate was stored on its record but the intake header's Attached "
            "Documents stayed empty and approval did not carry the file to the "
            "record. Inline files are now uploaded and attached to their section, "
            "the way a staff upload is."
        ),
    ),
    Patch(
        "openg2p_registry_partner_api/ingestion/helpers/request_response_helper.py",
        old="            return JSONResponse(content=response.model_dump())\n",
        new="            return JSONResponse(content=response.model_dump(mode=\"json\"))\n",
        why=(
            "Without a response template the envelope is dumped with its "
            "datetime timestamp intact, which JSONResponse cannot encode, so "
            "/partner/ingest_data answered 500 after storing the data. For a "
            "data model with no response template the ingest then looked "
            "failed to its sender: the ODK connector re-sent the same "
            "submission on every poll."
        ),
    ),
]


def main() -> int:
    applied = 0
    for patch in PATCHES:
        if not patch.path.exists():
            print(f"[patch-platform] SKIP (no such file): {patch.path}")
            continue

        source = patch.path.read_text()
        count = source.count(patch.old)

        if count == 0:
            if patch.new in source:
                print(f"[patch-platform] already applied: {patch.path.name}")
                continue
            print(
                f"[patch-platform] FAILED: no match for {patch.old!r} in "
                f"{patch.path.name}. The pinned platform likely changed -- "
                f"re-check whether this patch is still needed.",
                file=sys.stderr,
            )
            return 1

        if count != 1:
            print(
                f"[patch-platform] FAILED: expected exactly one match for "
                f"{patch.old!r} in {patch.path.name}, found {count}.",
                file=sys.stderr,
            )
            return 1

        patch.path.write_text(source.replace(patch.old, patch.new))
        print(f"[patch-platform] applied to {patch.path.name}: {patch.why}")
        applied += 1

    print(f"[patch-platform] {applied} patch(es) applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
