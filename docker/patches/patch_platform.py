#!/usr/bin/env python3
"""Overlay fixes for the pinned registry-platform images.

Each entry is an async/await mismatch in openg2p_registry_core that the pinned
platform ships broken. Applied at image build time to every stage that installs
registry-core (staff-api, partner-api, celery), because the same package is
present in all of them.

Drop an entry here once the corresponding fix lands in the platform image the
RP_VERSION pin points at -- the script fails loudly if a patch stops matching,
so a stale entry surfaces on the next build rather than rotting silently.
"""

from __future__ import annotations

import pathlib
import sys

SITE_PACKAGES = pathlib.Path("/usr/local/lib/python3.12/site-packages")


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
