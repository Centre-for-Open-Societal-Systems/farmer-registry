# Native Farmer release contract

The legacy RP bump script is fenced on this native OAN candidate, including
`-n` and automatic latest selection. It cannot update the image parents,
their installed ABI and the immutable central chart/profile together. Help is
still available before tool checks. Nonnative legacy fixtures retain the old
path; this change does not update a version or mutate staging/local charts.

Run `python ci/validation/check_release_pins.py` for a read-only source report.
[native-release-contract.json](../ci/validation/native-release-contract.json)
records the four image parents, the registry platform images
`openg2p/openg2p-registry-{staff-api,partner-api,celery,db-seed}`, at the
central platform pin 1.2.2-rc.557, and checks their exact ARG/FROM lines and the
immutable central archive provenance. Existing legacy RP/chart lock checks are
retained for staging. The separate UI addon pin keeps its own package contract.

The platform images install registry-core and celery-worker 1.2.1; the Farmer
extension built here is 1.0.3+oan.1 (OpenG2P's Farmer extension 1.0.3 with the
OAN layer). These are explicit installed package versions, not values inferred
from RC tags. The native worker probe checks that package tuple remains
unchanged.

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
