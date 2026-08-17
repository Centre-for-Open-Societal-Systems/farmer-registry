# Local Docker Compose stack

Runs the whole Farmer Registry — including the real OIDC login chain — on a
laptop.

```bash
docker compose --env-file local/.env up -d --build
```

Then open the **Staff Portal at http://portal.localtest.me:3000** and log in with
`admin` / `admin`.

## Where this came from

This repo owns only the farmer domain; deployment is a Helm chart that assumes an
OpenG2P environment already exists. This stack is that environment, reconstructed
from the published charts:

| Chart | Supplied |
|---|---|
| `openg2p-registry` 0.0.0-develop.383 | The env contract for staff-api, partner-api, celery worker/beat, db-seed and staff-ui, plus the `iam-register` role/permission catalog (`local/iam-register/payload.json`, copied verbatim from the chart) |
| `openg2p-commons-base` | Postgres, Redis, MinIO and Keycloak wiring, and the `staff` realm layout |
| `openg2p-commons-services` | IAM, master-data and the `staff-portal` client contract |

Every environment variable here corresponds to one in those charts. The registry
chart is **not** self-contained: it assumes Postgres, Redis, MinIO, Keycloak, IAM,
master-data and the id-generator already run as the `commons-base` and
`commons-services` releases. This stack stands those up too.

`RP_VERSION` in `local/.env` must stay equal to `ARG RP_VERSION` in
`docker/*/Dockerfile` and to the `openg2p-registry` dependency version in
`helm/openg2p-farmer-registry/Chart.yaml` — the same lockstep `scripts/bump-rp-version.sh`
maintains.

## Why `*.localtest.me` and not `localhost`

Signing in is a real OIDC round trip across three origins — the portal, the IAM
staff API and Keycloak. IAM sets a session cookie the portal must also send, so
all three need a **common parent domain**; a cookie scoped to `localhost` cannot
be shared with another host. Keycloak additionally advertises one issuer URL that
has to be reachable, and identical, from both the browser and the containers.

`*.localtest.me` is public DNS that resolves to `127.0.0.1`. From the browser
those names reach the published ports; inside the compose network the same names
are declared as network aliases and resolve to the containers. One URL therefore
works from both sides.

This is why each browser-facing service publishes a host port **equal to** its
container port.

## Services

| Service | URL | Notes |
|---|---|---|
| Staff Portal UI | http://portal.localtest.me:3000 | `admin` / `admin` |
| Dashboard UI | http://dashboard.localtest.me:3001 | Reached from the portal's **Dashboard** header button |
| Staff API | http://localhost:8001/docs | 8000 is taken by IAM, which must publish its container port |
| Partner API | http://localhost:8002/docs | Does not start — see the upstream bugs below |
| Keycloak | http://keycloak.localtest.me:8080 | admin console `admin` / `admin` |
| IAM staff API | http://iam.localtest.me:8000/docs | |
| Master data API | http://localhost:8010/docs | Geo hierarchy |
| MinIO console | http://minio.localtest.me:9001 | `minioadmin` / `minioadmin` |
| Postgres | `localhost:55432` | user `postgres`, password `postgres` |

One-shot containers that exit 0 when done: `minio-init` (creates the `default`,
`templates` and `documents` buckets), `db-seed` (farmer register metadata, geo
hierarchy, the ~500-record demo set, record images, DCI templates) and
`iam-register` (registers the registry's 11 roles and 72 permissions into IAM).

The Staff Portal UI carries no farmer code, so `docker/staff-ui` is the platform
image with one change: a build step that adds the **Dashboard** header button.
The dashboard runs on its own origin and the portal ships prebuilt, so it can be
neither a portal route nor a portal component — the button is patched into the
compiled bundle instead. See [`dashboard-ui/README.md`](../dashboard-ui/README.md).

Not included: `bene-api` (the beneficiary portal API the chart also ships) and the
Superset dashboards, whose bundle is imported into a Superset this stack does not
run.

## Upstream bugs at RP_VERSION 0.0.0-develop.383

Both are in the platform images, reproduce without any farmer code, and affect a
Kubernetes deployment of this pin equally.

**`partner-api` does not start.** `openg2p_registry_core.controller_services`
imports `openg2p_registry_staff_api.helpers.data_policy_request_helper`, which the
partner-api image does not install, so gunicorn dies on `ModuleNotFoundError: No
module named 'openg2p_registry_staff_api'`. Reproduce against the base image
alone:

```bash
docker run --rm --platform linux/amd64 --entrypoint python3 \
  registry.gitlab.com/openg2p/registry/registry-platform/partner-api:0.0.0-develop.383 \
  -c "import openg2p_registry_core.controller_services"
```

**`get_subject_record` always fails** with `object NoneType can't be used in
'await' expression`, logged by the staff API and surfaced in the portal as a
`SYS-ERR-001 UNEXPECTED_ERROR` toast when a record is opened. In
`openg2p_registry_core/services/g2p_register_service.py` the synchronous
`_build_register_policy_condition` (defined at line 999) is called with `await` at
line 1670 — the three other call sites do not. It returns `None` when no data
policy applies, and awaiting `None` raises. The register list and the record page
itself use other endpoints and are unaffected.

## Integrations that are switched off

These are `commons-services` components with no counterpart here. Each is
disabled through its documented flag rather than left pointing at a host that
does not resolve — see the bottom of `local/.env`.

| Integration | Flag |
|---|---|
| AWE (approval workflow) | `AWE_ENABLED=false` |
| Audit manager | `AUDIT_ENABLED=false` |
| Partner signature validation | `PARTNER_SIGNATURE_VALIDATION_ENABLED=false` |
| Consent manager | `CONSENT_ENFORCEMENT_ENABLED=false` |
| Keymanager auth | `KEYMANAGER_AUTH_ENABLED=false` |

The farmer approval ladder in `farmer-extension/.../awe_meta_data/`, partner-signed
DCI calls and consent enforcement therefore do not work locally, and the portal's
approval-tasks stats card reads "Failed to load stats" because
`/v1/awe/tasks/stats` has nothing to answer it. Everything else — the registers,
records, intake forms, geo widgets, the completion-score workers and the DCI
templates — does.

## Notes and limitations

- **Everything is emulated.** The OpenG2P base images publish `linux/amd64` only,
  so on Apple Silicon every registry service runs under emulation. First start is
  slow. Keycloak, Postgres, Redis and MinIO use multi-arch images and run
  natively.
- **db-seed loads the geo hierarchy, not the Master Data chart.** The registry
  chart sets `loadGeoData: false` because a real environment seeds the hierarchy
  through `geoSeed.countryPack` in the `openg2p-master-data` chart, which this
  stack does not run. `LOAD_GEO_DATA=true` uses db-seed's own loader instead: it
  writes the pack (5 levels, 884 units) straight into the `master_data`
  database, so the hierarchy is there and the dashboard's coverage denominators
  resolve. `LOAD_ATTRIBUTES` and `SYNC_GEO_WIDGETS` stay off — those copy code
  lists through the MDS *API*, which holds none.
- **Keycloak is 24.0.4** and it is the upstream image rather than
  `openg2p/keycloak`. The upstream image is multi-arch and supports
  `--import-realm` directly; the only thing lost is the openg2p login theme.
- **The portal's CSP is overridden.** Left to itself the staff-ui image appends
  `upgrade-insecure-requests` to the policy it builds from the `CSP_SRC_*`
  variables, which makes the browser reissue every stylesheet, script and image
  over https. Nothing here serves TLS, so all of them fail and the portal is
  stuck on its "Loading..." shell. `CSP_HEADER` on the `staff-ui` service
  replaces the generated policy outright and is that same policy without the
  upgrade directive. A deployment behind TLS should drop the override and let the
  image build the policy itself.
- **Ports are baked into two files.** `local/keycloak/realm-staff.json` and
  `local/iam/login_providers.json` contain absolute URLs, so changing
  `STAFF_UI_PORT`, `IAM_PORT` or `KEYCLOAK_PORT` in `local/.env` means updating
  those too.
- **One registry stack at a time.** Keycloak, IAM and MinIO must publish fixed
  ports, so this cannot run alongside another OpenG2P registry's local stack.

## Resetting

```bash
docker compose --env-file local/.env down          # keep data
docker compose --env-file local/.env down -v       # wipe databases and MinIO
```

Note that `down -v` also discards the Keycloak realm, which is re-imported from
`local/keycloak/realm-staff.json` on the next start, and the seeded records, which
`db-seed` reloads.

## Requirements

Docker needs roughly **8 GB or more** of memory; Postgres has been observed
crashing mid-import at Docker's 4 GB default.
