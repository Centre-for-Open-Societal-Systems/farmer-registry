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
