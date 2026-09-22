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
