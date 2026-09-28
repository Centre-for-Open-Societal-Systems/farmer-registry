# commons-services (shared platform services) in `far`

The farmer registry depends on the shared OpenG2P platform services — IAM,
Keycloak, AWE, Master Data — installed as the Helm release `commons-services`
in the same namespace. That release was originally installed by hand. This
directory puts the parts the farmer registry depends on under version control,
so a change to the shared services is reviewed in a pull request, and gives it
its own job to run from — deliberately **not** a stage of the registry's
per-build pipeline: the shared services change on their own cadence, and the
chart's post-upgrade hooks (geo seed, iam-register) re-run on every
`helm upgrade`, even a no-op one.

| File | Purpose |
| --- | --- |
| `upgrade.sh` | The upgrade, end to end. Pins the chart version. Run once per environment. |
| `Jenkinsfile` | Standalone, manual-only Jenkins job that runs `upgrade.sh` with the cluster's kubeconfig credential. |
| `values-far.yaml` | Values overlay layered on the release's live values. Only what the farmer registry needs from the platform. |
| `master-data-schema-topup.sql` | Idempotent `ADD COLUMN IF NOT EXISTS` set for Master Data, generated from the target image's models. Run inside the master-data-api pod before the upgrade. |
| `apply-sql-in-pod.py` | Runs SQL from stdin inside the master-data-api pod, using the DB settings from the pod environment (either prefix). |
| `seed-locations.sh` | Loads the Ethiopia location hierarchy into a namespace's Master Data, additively. See [Location hierarchy](#location-hierarchy). |
| `migrate-far-geo.sh` | One-time: moves `far` off the chart's ETH pack and the Kamuntu sample country onto that hierarchy, remapping farmer records. |
| `geo-common.sh`, `geo/*.sql` | The SQL and helpers both scripts run, each file headed with what it does and why. |

## Before you run this against staging — two blockers found 2026-09-23

Both were established read-only against the live `commons-services` release
(namespace `commons`, revision 9, chart `openg2p-commons-services-2.2.0-patched1`).
Neither is fixed. **`upgrade.sh` is unsafe on that release until they are.**

**1. The release's "user-supplied" values are 216 KB of frozen computed defaults.**

```sh
helm -n commons get values commons-services --revision 9 -o yaml | head -1
# COMPUTED VALUES: null
```

That first line is the header `helm get values -a` prints. Someone dumped an earlier
revision's *computed* values and fed the output back as a `-f` file, so the parser read
the header as a null-valued key and everything beneath it became a user-supplied
override — 16 top-level keys, every subchart's entire default tree, against an umbrella
`values.yaml` of 37 KB.

`upgrade.sh` preserves live values **by design** (step 1). Running it would therefore
pin every 2.2.0 default as an explicit override on top of the newer chart, silently
overriding defaults the new chart depends on. That is worse than the AWE issuer loss
below, and it is invisible in review because the diff is framed as "we kept your
values". **The 2.3.x plan starts by reducing those values to genuine overrides, not
with the upgrade.**

**2. `2.2.0-patched1` cannot be rebuilt, and the patch is not in any source.**

The patch is a **single missing newline** in the vendored `openg2p-master-data`
subchart (`templates/gen2-master-data-api/deployment.yaml`, line 29):
`{{- include "gen2MasterData.imagePullSecrets" . | nindent 6 }}` emits no trailing
newline and the following `{{- if .Values.hostAliases }}` chomps the separator, so when
an image pull secret is set while `hostAliases` and `affinity` are both empty, stock
renders `- name: ecr-pull-secretaffinity:` and the manifest **fails to parse at all**.

It is unrecoverable from the cluster: a Helm release secret stores the umbrella chart
but no subchart bodies, and all 13 umbrella templates are byte-identical to stock.
`helm dependency build` would fetch the buggy subchart (published
`openg2p-master-data 0.0.0-develop.26` is byte-identical to stock); it fails first
anyway, because the stored `Chart.yaml` names the dependency by its alias (`masterData`)
while `Chart.lock` uses `openg2p-master-data`.

This is an upstream chart bug worth filing — every installation hitting that values
combination is affected, and `patched1` exists only because someone hit it and patched
around it without publishing the result. If that artifact surfaces, the proper chart
path reopens.

**Consequence for `values-far.yaml`:** the master-data auth values it now carries
(`COMMON_AUTH_REDIS_URL`, `global.authProviderApiUrl`) were applied to staging by hand
with `kubectl set env`, because no safe chart path existed. That is drift on a
Helm-managed Deployment and any upgrade reverts it — which is exactly why they are in
the overlay, so the upgrade puts them back rather than undoing them.

## Running it

**From Jenkins (preferred).** Create a Pipeline job once, "Pipeline script
from SCM", script path `ci/commons-services/Jenkinsfile`, branch `develop`.
It has no triggers; run it with *Build with Parameters*: `ENVIRONMENT`
(`dev` → `gen2-dev-kubeconfig`, `staging` → `staging-farmer-kubeconfig`),
optional `CHART_VERSION` override, and `CONFIRM` ticked. Untick `CONFIRM` and
the job stops before touching the cluster. The live values it saved before
upgrading are archived with the build.

**By hand**, with that cluster's kubeconfig:

```sh
KUBECONFIG=/path/to/kubeconfig ci/commons-services/upgrade.sh
```

Either way the script upgrades an existing release only: it stops if
`helm get values` finds no `commons-services` release. A first install of the
platform is a deliberate act with the full values, not something this does.

## What `upgrade.sh` does, in order

1. Saves the live values next to the script as
   `commons-services-values-rev<N>.yaml` and prints the current revision with
   the exact `helm rollback` command.
2. Runs `master-data-schema-topup.sql` through `kubectl exec` in the
   *current* master-data-api pod: the pod already holds the database
   credentials in its environment (under either the old `GEN2_MASTER_DATA_API_`
   or the new `MASTER_DATA_API_` prefix — the snippet accepts both) and ships
   `asyncpg`, so nothing is copied out of the cluster.
3. Renders the upgrade (`helm template`) and lists the resulting images.
4. `helm upgrade` with live values + `values-far.yaml` at the pinned chart
   version, capturing hook pod logs and printing them if it fails.
5. Waits for the master-data-api rollout and checks, from the staff-ui pod,
   that the master-data behind `MASTERDATA_BACKEND_API_URL` now serves
   `/geo/get_all_geo_levels`. A missing route is a failure.

## After the upgrade: AWE issuers

AWE validates a token's issuer against `keycloak.issuer` plus
`keycloak.additional_issuers` in ConfigMap `commons-services-awe-config`. The
chart templates the first only, so this upgrade rewrites that ConfigMap and
drops any issuer added by hand — in `far`, the public portal's Keycloak. AWE
keeps serving until its pod restarts, which this upgrade does, and then answers
401 `Invalid issuer`, which the registry surfaces as `AWE-ERR-006` on the
Location and task widgets.

Step 6 of `upgrade.sh` prints the issuers AWE ends up with. If an environment is
reached through a Keycloak hostname that is not among them, add it back:

```sh
kubectl -n far get cm commons-services-awe-config -o jsonpath='{.data.config\.yaml}' > awe.yaml
# add the issuer under keycloak.additional_issuers, then:
kubectl -n far create configmap commons-services-awe-config \
  --from-file=config.yaml=awe.yaml --dry-run=client -o yaml | kubectl -n far replace -f -
kubectl -n far rollout restart deploy/commons-services-awe
```

## Rollback

`helm -n far rollback commons-services <revision printed in step 1>`. The
schema top-up is additive and harmless to the previous build, so it needs no
undo.

## Location hierarchy

The staff portal's Location section cascades Region → Zone → Woreda → Kebele
out of Master Data. `far` carries the same Ethiopia hierarchy the local stack
and the cropsown registry use: `docker/local-dev/geo-seed/ethiopia_geo_seed.sql.gz`,
21,053 locations (14 / 125 / 1,379 / 19,535), ids `<level>-<P-code>`
(`region-ET01`, `zone-ET0101`, `woreda-ET010101`, `kebele-…`), parents linked by
id. It is **not** the chart's ETH country pack. The pack stops at woreda, uses
bare P-codes as ids (`ET01`), and names its levels region/zone/woreda. Those
names are UNIQUE in `g2p_geo_levels`, so the two cannot share a database. That is
why `values-far.yaml` sets `geoSeed.load.geo: false` (the hook still loads code
lists) and `samples: false` (the pack's sample people carry pack ids), and
pins `countryPack: ETH` (the subchart default is `XKM`, the fictitious Kamuntu).

Both scripts run from the Jenkins job (`ACTION`) or by hand, inside the
namespace's `commons-postgresql-0` as the superuser. That is the one place that
reaches both `master_data` and the registry's own database. `DRY_RUN` defaults
to true: every transaction runs to the end, guards included, and rolls back.
Readings (levels, counts per level, orphan parents, which id scheme the
registry's records point at, and every trace of Kamuntu) are printed before
and after.

**`seed-locations.sh`** — additive only. `DO NOTHING` on every conflict; an
existing location keeps its id and every column. It runs the schema top-up in
the same transaction, since older Master Data builds lack `display_name` & co.,
and it aborts, changing nothing, when the namespace holds a hierarchy it cannot
sit next to:

- **`far` before migration.** The pack's level names collide. Run `migrate-far-geo.sh`, which runs this step itself.
- **`live`.** The livestock registry's own db-seed loads a *variant* of this file into `live` on every run. That variant links each parent by **name**, keeps names unique (dropping the ~2,080 locations whose name repeats), and adds a unique index on `level_value_mnemonic`. This is deliberate: livestock's Location widget cascades by name, and its records store names, not ids (see the header of `livestock-registry/docker/db-seed/geo/ethiopia_geo_seed.sql.gz`). Loading id-linked rows there would empty its Zone/Woreda/Kebele dropdowns. Moving livestock onto ids is a change to its widget config and records, in that repository, not here.

**`migrate-far-geo.sh`** — one-time, three transactions. They run in an order
that keeps every id the registry references resolvable at every moment:

1. `master_data`: rename every level the seed does not define to `legacy_*`,
   then load the seed next to it.
2. `farmer_registry`: remap every record. Every table with
   `geo_lowest_level_value_id` is found through `information_schema`: register,
   history and intake-form tables. `geo_code_hierarchy_json`,
   `woreda_level_value_id` and `region/zone/woreda/kebele_name` are rewritten
   together, and change-request payloads get the same rewrite per snapshot.
   Mapping rules:
   - pack id → `<level>-<P-code>` (the pack's id *is* the P-code).
   - Kamuntu id → a real kebele, picked from `md5(old id)`, so every table
     sharing an old id lands on the same kebele and a re-run picks the same one.
   - Anything else aborts.
   - Kamuntu's country code `KM` becomes `ET` everywhere.

   The full old → new list is printed; it is the audit trail.
3. `master_data`: delete the `legacy_*` levels and their locations, but only
   after checking that the registry references none of them. This is the only
   DELETE, scoped by level and never by "not in the seed".

Phases 2 and 3 end with a scan for Kamuntu across every text/json column of the
database, and any hit aborts. A real run first dumps the affected tables of both
databases to `far-geo-backup-*.sql.gz`, which the job archives: that is the
rollback. Afterwards, re-run the farmer db-seed hook (`syncGeoWidgets` matches
the intake form's widget to the new levels) and refresh the `fr_rpt_*` views.

Order: dev first, `DRY_RUN` then real, then staging the same way. On staging
compare the dry run's readings with dev's before unticking: real records there
may reference ids the mapping rules do not cover, and the run aborts on those
by design.

## Regenerating the schema top-up

Whenever the chart pin moves the master-data image, regenerate the SQL from
that image so it matches the models the seed will write:

```sh
IMG=registry.gitlab.com/openg2p/platform-services/master-data-service/master-data-api:<tag>
docker run --rm -i --entrypoint python "$IMG" - <<'EOF' > ci/commons-services/master-data-schema-topup.sql
import os, importlib, pkgutil
os.environ.setdefault("MASTER_DATA_API_DB_HOSTNAME", "x")
from sqlalchemy.dialects import postgresql
import openg2p_gen2_master_data.models as m
for mod in pkgutil.iter_modules(m.__path__):
    importlib.import_module(f"{m.__name__}.{mod.name}")
from openg2p_fastapi_common.models import BaseORMModel
d = postgresql.dialect()
print("BEGIN;")
for t in BaseORMModel.metadata.sorted_tables:
    for c in t.columns:
        typ = c.type.compile(dialect=d)
        if not (c.nullable or c.primary_key):
            print(f"-- SKIPPED (NOT NULL, must already exist): {t.name}.{c.name} {typ}")
            continue
        print(f'ALTER TABLE IF EXISTS public.{t.name} ADD COLUMN IF NOT EXISTS "{c.name}" {typ};')
print("COMMIT;")
EOF
```

Then put the explanatory header back at the top of the file.

## Why 2.3.0-rc.217

Of the chart versions that render the `MASTER_DATA_API_*` names,
`2.2.2-rc.214` and `2.3.0-rc.217` pin the same subcharts (master-data
1.1.0-rc.55, IAM 1.4.0-rc.90, audit-manager 1.0.1) but rc.214 still overrides
the IAM images to the bare floating `develop` tag; rc.217 lets the IAM subchart
own them. `0.0.0-develop.231` floats every service on `develop.*` tags. The
master-data image was verified directly: `1.1.0-rc.55` serves
`/geo/get_all_geo_levels` and `/geo/get_geo_level_values`, reads
`MASTER_DATA_API_*`, and its geo model matches its own seed.
