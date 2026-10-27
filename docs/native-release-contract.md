# Native Farmer release contract

The legacy RP bump script is fenced on this native OAN candidate, including
`-n` and automatic latest selection. It cannot update native Farmer parents,
their installed ABI and the immutable central chart/profile together. Help is
still available before tool checks. Nonnative legacy fixtures retain the old
path; this change does not update a version or mutate staging/local charts.

Run `python ci/validation/check_release_pins.py` for a read-only source report.
[native-release-contract.json](../ci/validation/native-release-contract.json)
records four native Farmer image parents at 1.2.1-rc.192 and the independent
central platform pin 1.2.2-rc.557. It checks exact ARG/FROM repositories and
immutable central archive provenance. Existing legacy RP/chart lock checks are
retained for staging and their misleading bump-script failure hints are fixed.
The separate UI addon pin keeps its own package contract.

Hosted worker initialization observed installed registry-core and celery-worker
distributions 1.2.1 and Farmer extension 1.0.3 in the current native parent.
These are explicit observed package versions, not values inferred from RC tags.
The native worker probe checks that package tuple remains unchanged. Farmer
parent and platform tag numbers must not be treated as equal versions.

Package versions alone do not establish ABI compatibility. The native worker
save/rollback gate is required alongside worker/beat registration, ORM DDL,
metadata replay and real built-image checks. Its result must be read for the
exact source/image head; registration-only or API-initialized tests cannot stand
in for native worker-save acceptance. Current probe failures remain blockers.
No FINAL/AWE/login/live MDS/filestore acceptance is claimed by the bounded save
probe, and no API engine injection or worker replacement is allowed.

Future release changes need explicit reviewed parent/platform/archive inputs,
resolved image provenance and a fresh complete hosted acceptance run. Automatic
latest discovery is not a native-candidate release mechanism. Existing recovery
and external legacy callers need their own reconciliation before the retained
chart cleanup gate can be lifted. This is OAN delivery validation only; no
OpenG2P framework, worker, package source or RC pin was changed.
