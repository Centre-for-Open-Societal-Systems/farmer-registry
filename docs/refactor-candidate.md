# Farmer refactor delivery candidate

This review branch composes native extension source `d37526ac23fb2380b491c7ba351d7e3e8793f683` with the existing
COSS delivery base `75bb62b58d6ee5a3bd398be40d4ad9a80b5f88ca` and the changes described here. It does not merge
legacy core/worker implementations into the native refactor source branch.
Working primary checkouts and the local runtime worktrees remain separate.

## Verification boundary

The candidate uses OpenG2P rc.557 extension contracts, registered widgets and
metadata. No platform source, worker replacement or compiled-asset patch is
introduced. Runtime selection must be identical in APIs, ingestion workers and
beat. Dashboard UI/API are independently owned COSS repositories; connector
source retirement does not remove its running release or checkpoints.

Helm is owned by COSS oan-helm. The candidate profile pins dev.14 at
`c08497721ec93eda0b19c2a504255b1ea8a00d8f`, including the chart archive SHA-256.
The three archives were fetched from that immutable URL and their hashes verified
on 26 October 2026. All registry promotion flags remain false.

Since the identity change of 28 October 2026 the Fayda ID is typed on the intake
form and the record is verified with the platform's `id-authentication` widget;
the OAN popup widget and its server code are gone. A backing value is not
verification. The signed Farmer-reference lookup contract remains separate.

Existing Jenkins agents, credentials, ECR paths and preservation tooling remain.
PR and feature-branch validation do not deploy. First New Dev reset requires the
reviewed per-registry manifest, durable external receipt, producer pause, verified
backup/restore, explicit initialization or recovery and accepted seed checks.
Ordinary deployment requires the matching VERIFIED receipt. No operational reset
manifest has been provisioned or executed by this candidate. Staging requires its
own preservation rehearsal.

Hosted native image, PostgreSQL replay and browser checks must pass on the exact
candidate commit. Earlier source/build receipts are dated evidence, not proof of
this commit. Real eSignet, signed consent lookup, both approval orders, independent
Kafka-created AWE tasks, imports/ODK, geographic denial, reporting and restored-copy
acceptance remain promotion requirements. A missing supported hook is a blocker.

Local runtime acceptance is serial: Commons + Farmer + Crop, then Commons + Farmer
+ Livestock. No New Dev or staging application/data was changed by preparing this
branch. The current local Docker control failure prevents fresh native containers;
running HTTP applications and source checks have separate evidence.

## Farmer ODK and reporting scope

The registered enricher maps the source form into 16 native sections, stores
attachments through the native document handler and leaves transaction ownership
to ingestion. Multi-answer fields preserve every selected income, water, machinery
and finance value. Added catalogue codes have a separate OAN data PR; its preview
seed publication and real catalogue acceptance remain outstanding.

The v3 XLSForm is an unpublished candidate, validated separately from live Collect.
Its [explicit plot-selection follow-up](odk/ATI-LAND-LINKS-20261026.md) now covers
main crop/livestock/input parent selection through standard ODK controls.
The [102-question mapper audit](odk/ATI-MAPPER-AUDIT-20261026.md) records remaining
additional Farmer repeat, household-reference branch,
consent event, optional email and geography gaps. A retained raw payload does not
establish complete domain functionality.

Registry-owned reporting SQL reads native crop holdings and retains legacy view
names. Replays preserve reader grants and reject unknown dependencies. Geographic
labels come from authenticated Master Data HTTP, with the existing per-registry
client and Secret references. The central chart renders one reporting Job.
Fresh hook execution and authenticated dashboard acceptance remain outstanding.

APIs, worker and beat share the same idempotent OAN component registration.
Worker and beat load it through native `CELERY_IMPORTS`, retaining their native
engines; the API initializer is not invoked inside Celery.
Offline launcher checks require the same intake, signature and JSON-safe approval
services while preserving native schedules; hosted verification remains required.
