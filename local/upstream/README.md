# Local COSS trial on the upstream RC architecture

This checkout adopts the upstream Farmer repository layout and published
registry-platform `1.2.2-rc.544` components. COSS adds domain models, validation,
metadata, translations and ODK mapping in `farmer-extension/`, `translation/`
and `odk/`. The registry UI inherits rc.544 with a small COSS intake overlay.

[Source and image provenance](source-manifest.json) records the upstream layout
commit, COSS source commit and locally resolved image identities. The source
layout comes from upstream's current repository; runtime components and the
registry chart dependency are pinned to RC, not development images.

## Ownership

| Compose project | Owns |
| --- | --- |
| `farmer-upstream-commons-base` | PostgreSQL, shared Redis, Keycloak, MinIO, optional Kafka |
| `farmer-upstream-commons-services` | IAM, master data, partner management, consent management, approval workflow, shared portal, optional audit service |
| `farmer-upstream-registry` | Farmer APIs, worker/beat, private task queue, ID generator, stock registry UI, COSS seed and sanity tests |

The shared portal is an application launcher. The registry staff UI is the
platform's metadata-driven registry application. Both are needed. The registry
image adds guarded adapters for photo persistence, certificate display and GC/EC
labels; it does not carry a separate frontend source tree.

The trial follows the component contract used by Commons Base 2.3.3 and Commons
Services 2.3.4-rc.245. These are local Compose equivalents, not installations of
the Commons Helm releases. The single `compose.template.json` is the input;
`stack.py` renders independently managed projects and removes dependencies that
cross project boundaries. Startup ordering handles those shared dependencies.
The projects share only the dedicated `farmer-upstream-trial` Docker network
and explicit service endpoints. Databases are separate within the trial's
PostgreSQL instance. The registry task queue is separate from shared Redis.

## Run

Requirements: Docker Compose with `run --env-from-file`, Python 3.12+, and enough
Docker memory for the shared services. From the repository root:

```sh
python local/upstream/stack.py validate
python local/upstream/stack.py init
python local/upstream/stack.py status
python local/upstream/stack.py test
```

`init` builds the Farmer images, starts Base, configures Keycloak and storage,
starts Services, installs portal catalogs, explicitly checks registry migration,
loads the COSS geographic override and configuration, then starts Registry.
SQL seed errors stop initialization. Identical SQL seeds are skipped using a
checksum ledger; changed applied SQL requires an explicit migration or a fresh
trial. Geo synchronization and template uploads run again on each seed.

```sh
python local/upstream/stack.py stop
python local/upstream/stack.py up
python local/upstream/stack.py stop registry
python local/upstream/stack.py up registry
python local/upstream/stack.py seed
```

Ordinary stop/start preserves all trial data. `init` is for setup, while `up`
restarts an initialized environment. Rebuild after changing domain code.

For an intentional fresh trial only:

```sh
python local/upstream/stack.py reset all --confirm-trial-reset
python local/upstream/stack.py init
```

Reset removes only the four explicitly named `farmer-upstream-trial_*` volumes.
It never targets the original local stack or a remote server. No existing farmer
records were restored into this trial. Sanity tests create synthetic records.

## Review

- Registry: <http://portal.farmer-upstream.localtest.me:3200>
- Commons portal: <http://staff.farmer-upstream.localtest.me:3202>
- Keycloak: <http://keycloak.farmer-upstream.localtest.me:8180>
- Local staff login: `staff` / `staff`; local administrator: `admin` / `admin`.

All exposed ports bind to localhost. Credentials and the consent signing
certificate in `assets/` are public local-demo fixtures. They are not deployment
secrets. `generated/` contains runtime configuration, logs, screenshots and any
browser sessions and is ignored by Git.

## Evidence and remaining work

Verified on 2026-10-15:

- All three Compose configurations validate; core containers start.
- The full `init` rerun finishes successfully, including migration, seeding,
  template upload and registry readiness checks.
- Registry Dockerfile/chart RC pins match (one upstream guard test passed).
- COSS metadata seed completes and an identical rerun completes.
- Live API suite: **11 passed, 2 skipped**. Passed checks include smoke,
  negative authorization/consent cases, DCI search, change approval/history and
  staff intake save/readback/approval.
- Browser login reaches the shared portal and stock Farmer dashboard; the
  Farmer list displays the synthetic records without HTTP failures.

The skipped checks are ODK submission/attachments/approval and audit persistence.
These are not established by the passing intake API check.

Registry UI image extends rc.544 with the scoped intake overlay in
`docker/staff-ui/`. Build guards require each patched RC integration point to
match exactly once. Changed static bundles are rehashed; the overlay script has
a content-based URL. The shared portal has a local HTTP-only CSP
adjustment (`assets/staff-portal-http.js`). The COSS Python extension still has
its inherited filter-builder and image URL compatibility hooks; this is not a
claim of metadata-only customization. No general backend platform patch script
is included.

## COSS geography and intake acceptance

`assets/geo/ethiopia_geo_seed.sql.gz` is the supplied COSS geographic catalog:
14 Regions, 125 Zones, 1,379 Woredas and 19,535 Kebeles (21,053 places). Country
is not a selectable level. Distinct places sharing a name and parent have their
P-code appended to the displayed label to satisfy the RC MDS uniqueness rule.

`geo_override.py` stages and validates the source, maps existing lowest-level
IDs and hierarchy JSON by level/P-code, then installs the catalog. An unmappable
existing selection aborts before changes. The initial migration preserved the
existing Zana draft as `woreda-ET010103`. A version/checksum record prevents
ordinary reseeding from restoring the upstream ETH catalog.

`stack.py seed` stops running Registry services during seeding and restarts them
only on success. It leaves writers stopped after failure. The MDS and Registry
commits span separate databases; a recovery journal in ignored `generated/`
records the previous catalog and changed rows before either commit. If a process
fails between commits, initialization stops for explicit reconciliation; do not
delete the journal or restart writers until both databases are reconciled.

Browser acceptance creates synthetic drafts and uses the real services. Install
Playwright or set `PLAYWRIGHT_MODULE` to an existing module; optionally set
`CHROME_PATH`, then run `node local/upstream/browser_acceptance.cjs`. Results and
screenshots are written to ignored `generated/`. The test deliberately simulates
an upload failure to check that the previous saved attachment survives.

The upstream CI and Helm wrapper are preserved for review. Publishing targets,
analytics compatibility, a full Helm render and COSS release permissions still
need validation before using this as a deployable release. No images, commits,
PR changes or server changes are published by these commands.
