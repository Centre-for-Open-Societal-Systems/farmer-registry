# Local Commons / Farmer split

This is a **migration setup for the existing local stack**, in two Docker Desktop
Compose groups. It does not install or modify the development server. Use this
directory from the `feat/gen2-common-rc245` worktree, not the separate `develop`
checkout. Generated files contain absolute paths to the worktree that rendered
them; regenerate after moving the checkout.

| Project | Services |
| --- | --- |
| `openg2p-shared` | Existing Postgres, Redis, Keycloak and mail; MinIO, IAM, Master Data, AWE, PM, CM and their UIs; optional Kafka/audit |
| `farmer-registry` | Staff/partner APIs, staff UI, worker/beat, persistent private queue, ID generator; optional seed/reporting/dashboard API |

Image pins come from the published **Commons Services 2.3.4-rc.245** chart.
The recorded server has Commons Base **2.3.3**. Locally we retain Postgres 16,
Redis 7 and Keycloak 26.0 so existing database volumes are not subjected to an
unrelated engine upgrade. This mirrors service ownership and application
contracts; it is not a reproduction of Kubernetes controllers, Helm hooks, all
optional Commons products, TLS or the server's infrastructure image builds.

`render.py` reuses the repository's existing service/build definitions, selects
each project's owners, and applies the local wiring. `commons-services.yaml`
defines the additional published services. No sibling untracked `shared-infra`
files or source clones are needed to **render** it. The optional dashboard image
must already be built from its separately maintained repository.

## Prepare and verify without starting services

Python 3.11+ with `pip install -r ci/gen2/requirements.txt`, plus Docker Compose v2:

```text
python local/gen2/stack.py validate
python -m unittest discover -s test -p test_gen2_local.py -v
```

`validate` uses the real Compose parser but does not need the engine. The tests
check ownership, dependency graphs, persistent volumes, opt-in jobs, auth URLs,
queue separation, image pins, and a startup failure that prevents deployment.
The image provenance test needs the published chart under `.cache/gen2-charts/`;
CI already downloads it. It skips explicitly if that artifact is absent.

Copy `.env.example` to `.env` here only if overriding the local defaults. Both
files contain local development configuration. Do not use real server secrets.
`cm_signing_demo.p12` is the **public test key** supplied by the pinned Commons
chart (password `openg2p`). Both CM audiences mount that same stable key; receipts
do not depend on a new ephemeral signing key after each restart. The three
`*-catalog.json` files carry the chart's IAM catalogs, with decorative icons
omitted. Farmer's catalog is reused directly from `local/iam-register/`.

## Cutover of the existing local environment

Do not run the old `openg2p.sh up farmer` concurrently with this setup. It owns
the previous Compose configuration and could recreate services under Farmer.

1. Record `docker compose ls --all` and the current image IDs. Pause incoming
   requests and stop the old Farmer beat and other ingestion producers. Let its
   worker finish queued and reserved work, then stop it and Farmer APIs/UI.
   The runner checks the old DB 4 queues and unacknowledged deliveries before
   starting Farmer. If custom Celery priority queues are in use, check/drain
   those too. Do not clear Redis: DB 4 also contains IAM sessions.
2. Back up the existing PostgreSQL databases (including Keycloak, IAM, AWE,
   Master Data, PM and CM) and MinIO volume while writes are quiesced. Store
   exports under `local/gen2/backups/` (ignored) and rehearse restoration. There
   is no automatic backup, restore, database reset or data repair in the runner.
3. Stop the previous commons instances in Farmer and `platform-services`:
   MinIO, IAM, AWE API/UI, Master Data, staff hub, PM and CM. Keep their stopped
   containers for reference. Do not remove volumes. The runner refuses to start
   while the known conflicting instances are still running.
4. Keep the existing `openg2p-shared-postgres`, `-redis`, `-keycloak` and `-mailpit`
   containers running. `shared-up` attaches them to `openg2p-gen2` with service
   aliases without recreating them or altering their existing network. Other
   registries keep their original paths. MinIO adopts the existing external
   `farmer-registry_minio-data`; Postgres retains
   `openg2p-shared_postgres-data`. The runner fails if either volume is absent.
5. Start and explicitly initialize the shared additions, then build/check Farmer:

   ```text
   python local/gen2/stack.py shared-up
   python local/gen2/stack.py setup
   python local/gen2/stack.py build
   python local/gen2/stack.py check
   python local/gen2/stack.py farmer-up
   ```

`shared-up` starts published application images, whose upstream entrypoints may
run their own schema migrations. Backups are therefore required **before** this
step. The local database names remain `farmer_iam`, `farmer_awe`,
`farmer_master_data_db`, `partner_management_db`, `consent_manager_db`,
`farmer_registry_db`, and `farmer_idgenerator`. They are not renamed to the
server's names.

`setup` explicitly provisions the existing **farmer realm**'s local clients and
roles, ensures buckets, aligns local IAM login provider 1, and registers applications
through IAM's HTTP API.
It reuses the existing initializer, including its local test-user passwords;
it does not touch the livestock/crop realms. Ordinary startup does not rerun it.
The explicit provider update is needed because IAM only loads its JSON on an empty
database. Other provider rows are preserved. The shared hub removes only the
build-time `upgrade-insecure-requests` CSP directive for this HTTP environment.

`check` bypasses the staff image's normal entrypoint. It probes dependencies,
verifies the published issuer, and runs the existing read-only rc.544 coordinate
schema gate. Missing or varchar coordinate columns stop the upgrade. Rehearse
the coordinate migration on a restored database if needed; this runner will not
perform it. `farmer-up` repeats this gate before starting the application.

`python local/gen2/stack.py farmer-stop` stops only registry-owned containers.
The shared network is external to both projects and cannot be removed by their
normal Compose teardown. Prefer this stop command to running `down` during
cutover. Never use `down -v` or `--remove-orphans` here.

## Local URLs and contracts

| Service | Browser address |
| --- | --- |
| Shared hub | http://staff.farmer.localtest.me:3102 |
| Farmer UI | http://portal.farmer.localtest.me:3100 |
| IAM | http://iam.farmer.localtest.me:8100 |
| Master Data | http://masterdata.farmer.localtest.me:3110 |
| AWE | http://awe.farmer.localtest.me:8131 |
| PM | http://pm.farmer.localtest.me:3050 |
| CM | http://cm.farmer.localtest.me:3060 |
| Keycloak | http://keycloak.localtest.me:8080 |
| MinIO S3 API / console | http://minio.farmer.localtest.me:9100 / :9101 |

IAM and Farmer use shared Redis **DB 4** for sessions. Worker/beat use Farmer's
own persistent queue at `queue:6379/0`. AWE reaches callbacks over `openg2p-gen2`;
the callback URL stays `http://farmer-registry-staff-api:8000/awe/webhooks/decision`.
The issuer is the same browser-reachable Keycloak URL inside and outside Docker.
MinIO signing uses the browser-reachable hostname and port, preserving the Host
header covered by presigned URLs. Existing local bucket names are retained; do
not connect additional registries until their object-key isolation is checked.

Staff authentication/CSRF, partner signature validation and consent enforcement
are enabled. PM/CM staff APIs require auth. Their partner audiences use the
published public-key/signed-consent contracts, rather than staff login. Registry
AWE remains enabled; CM **policy-change** AWE gating remains disabled as in the
published default. DCI signature and consent success/failure tests passed locally. The legacy
`/partner/ingest_data` ODK path only checks partner registration in this pinned
platform: its presence of a signature field does **not** prove cryptographic
verification. Do not treat the DCI security tests as coverage of that endpoint.

## Optional jobs and services

Seeds never run on `farmer-up` or `shared-up`. Master Data owns the ETH geography
and code lists through `master-data-seed`; Farmer's seed disables geography,
samples and photos, retaining metadata/templates and widget synchronization.
Existing seed repeatability and data-linkage defects are still tracked in
`docs/gen2-db-seed-diagnosis.md`; do not rerun it on preserved data before that
work is tested on disposable databases.

The `reporting` profile contains the private dashboard API on `127.0.0.1:8105`.
The explicit `reporting-views` job has a separate `reporting-seed` profile and
runs the same SQL/geo scripts as Farmer's Helm job. The dashboard UI remains
independently hosted. Its service account/client roles must already exist.

The optional shared `audit` profile contains audit-manager 1.2.0 and a single
Kafka 3.9.0 broker/controller for a small local environment. Create its
`audit_manager` database explicitly if absent before starting that profile.
Set `AUDIT_ENABLED=true` in this directory's `.env` only after it is healthy,
then recreate the API services. Audit/Kafka remain off by default because the
recorded Docker allocation is 7.4 GiB. No audit-delivery guarantee is claimed
until event ingestion and persistence are tested.

## Local acceptance evidence (2026-10-14)

- SSH host-key trust was established against the previously recorded fingerprint.
  Commons releases/images were inspected read-only on the new server. Its Master
  Data API uses a custom development image; locally the published RC is used and
  its authenticated browser geography reads were verified.
- All shared services and Farmer started against preserved databases/volumes.
  IAM application registration and browser login passed for hub, Farmer, Master
  Data, PM and AWE. Farmer stop/start left shared services running.
- Thirteen live acceptance cases passed: smoke, consent denial, bad signatures,
  wrong consent audience, allowed/clamped DCI searches, change-request creation,
  two-stage AWE approval, history retention, audit persistence, staff intake and
  fresh ODK ingestion with photo/certificate promotion.
- Staff intake with numeric/string GPS input and a false household-head choice
  passed save/readback and AWE approval into the register. The test exposed a
  legacy coordinate normalizer that returned strings after rc.544 switched to
  Float columns; the normalizer now returns numbers.
- Local ODK Central/connector acceptance and detailed remaining limits are in
  [acceptance.md](acceptance.md). Test records are labelled `Genintaketest`,
  `Genodktest` and `SANITY-FARMER-0001`; no existing farmer was selected for edits.
- 73 Linux regression cases (plus 6 subtests), 14 local topology/lifecycle cases,
  12 domain-helper cases and the ODK transform assertions passed. Linux checks
  include actual Helm renders and the read-only preflight failure cases.

Generated logs/screenshots and local secrets stay in ignored `generated/`,
`.env` and `backups/` paths; none are published with the PR. Restore work is
outside the remaining acceptance scope at the user's direction. Seed hardening,
existing server data repair and server coordinate migration remain separate
work; this local validation does not authorize or perform a server deployment.
The branch includes upstream DevOps PR #92 (`67d47a8`) and retains its credential,
namespace and private dashboard routing. PR #91 is updated with this evidence.
