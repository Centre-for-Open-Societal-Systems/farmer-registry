# ODK ingestion for the farmer registry

Field agents submit the farmer profiling form from ODK Collect. ODK Central
holds the submissions; this connector polls Central and posts each submission to
the registry's Partner API, which queues it for the celery worker to turn into a
draft intake submission for staff to review.

```
ODK Collect → ODK Central → connector (poll) → partner-api → redis → celery worker → draft intake → staff review
```

crop and live already run this. Farmer uses the same chart and the same shape,
with its own images built by this repository's pipeline.

| Piece | Where |
| --- | --- |
| Connector service and UI | `openg2p-connector-service/`, `openg2p-connector-ui/` |
| Helm chart | `openg2p-connector-service/deploy/charts/openg2p-connector` |
| Values for `far` | `ci/connector/values-far.yaml` |
| Deploy | `ci/connector/deploy.sh` |
| The form, its media, and the field mapping | `odk/` |

## Activating it in an environment

**1. Build the images.** The pipeline builds `connector-service` and
`connector-ui` alongside the registry images, so any develop build produces
them. Take that build's tag.

**2. Deploy the release.**

```sh
ENVIRONMENT=far     KUBECONFIG=<dev cluster>     ./ci/connector/deploy.sh <image tag>
ENVIRONMENT=staging KUBECONFIG=<staging cluster> ./ci/connector/deploy.sh <image tag>
```

`ENVIRONMENT` picks `ci/connector/values-<environment>.yaml` and is required.
It used to be derived from the namespace, which is wrong here: dev and staging
are different clusters that both run the registry in a namespace called `far`,
so a staging deploy quietly used dev's values — dev's hostname, dev's database
and pull-secret names, dev's ODK URL — and came up looking healthy while
pointed at the wrong ODK server.

The chart creates the `farmer_connector` database and its user through its
`postgres-init` subchart, then starts the API, the worker, the beat scheduler
and the UI. The release keeps its own values on redeploy, so pipelines and
credentials set later are not overwritten.

**3. Register the partner.** The Partner API rejects an ingest whose
`partner-id` it does not know. In the `master_data` database:

```sql
insert into g2p_partners (partner_id, partner_mnemonic, keymanager_reference_id, is_active)
values ('farmer-partner', 'farmer-partner', 'farmer-key-ref', true)
on conflict (partner_id) do nothing;
```

**4. Publish the form.** In ODK Central, create the project, upload
`docs/odk/ATI_Farmers_Profile_ODK_Form_v2.xlsx`, attach `docs/odk/media/KebeleList.csv` and
`docs/odk/media/PrimaryCoopList.csv` as media, and publish. Note the project id and form id.

**5. Point the pipeline at it.** Either in the connector UI
(`https://connector-farmer-registry.far.openg2p.test`), or by setting these on
the release so the connector seeds the pipeline itself on first start:

| Setting | Example |
| --- | --- |
| `CONNECTOR_ODK_CENTRAL_BASE_URL` | `https://odk-central.oanstaging.com` |
| `CONNECTOR_ODK_PROJECT_ID` | the project holding the form |
| `CONNECTOR_ODK_FORM_ID` | the published form id |
| `CONNECTOR_ODK_CENTRAL_EMAIL` | an ODK Central account with access to it |
| `CONNECTOR_ODK_CENTRAL_PASSWORD` | mount from a secret, never in values |

Nothing is seeded until all five are set, and no credentials are built in.

These go under **`extraEnv`**, not `commonEnv` — see `values-staging.yaml`. The
`commonEnv` helper renders a fixed allowlist and silently drops anything it does
not name, so until `extraEnv` existed none of these could reach a container and
this seeding path could not work at all; every environment had to be configured
by hand in the UI. Put the password in `extraEnvFrom`, pointing at a secret.

## Checking it works

```sh
# the connector polled and posted
kubectl -n far logs deploy/farmer-connector-worker --tail=50

# the registry accepted and classified it
select ingest_id, data_model_id, transformation_status, ingestion_status
from incoming_classified_data order by classified_date_time desc limit 5;

# a draft intake appeared for staff to review
select submission_id, application_reference, approval_status
from g2p_intake_form_submissions order by first_created_at desc limit 5;
```

Then open the staff portal, review the draft under Intake Forms, and approve it
to commit the record to the register.

## The registry side

The connector wraps each submission as
`{header: {message_id, sender_id: "farmer-partner", ...}, message: {payload: <submission>}}`
and posts it with `?data_model=FARMER_ODK_MODEL`. The registry turns that into an
intake with nothing but seed data, all applied by db-seed:

| Piece | Where |
| --- | --- |
| Data model, key paths, semantic pattern (Farmer Ingestion Intake form), template routing | `farmer-extension/.../meta_data/registry-inbound-message-rules/zz_farmer_odk_ingestion.sql` (the same rows, same ids, as `odk/setup_farmer_odk_connector.sql`, so a hand-seeded environment and a db-seeded one agree) |
| The transform, ODK submission to intake sections | `odk/templates/farmer_transform.j2`, uploaded to the `templates` bucket (`LOAD_TEMPLATES`) |
| Check of the transform against an OData-shaped submission | `python odk/test_transform.py` (needs `jinja2`) |

Two fixes to the pinned platform make the path work at all (`docker/patches/patch_platform.py`):
the celery worker now creates the services the intake save reaches through
`get_component()` (and the fastapi-cache backend), and the Partner API can encode
its response when a data model has no response template. Without the first,
every ingest stopped at `ingestion_status=FAILED`; without the second, the
connector saw a 500 for every submission and re-sent it on each poll.

Approval: the worker finalizes each draft as a staff Submit does, which starts
the intake's AWE approval workflow, so approvers get a task (status PENDING with
an AWE request). The worker has no user, so it logs in with a client-credentials
token: `REGISTRY_CELERY_WORKERS_AWE_TOKEN_URL` / `_CLIENT_ID` / `_CLIENT_SECRET`,
plus the AWE settings the staff-portal-api uses, as `REGISTRY_CELERY_WORKERS_AWE_*`
(the worker reads the platform settings under its own prefix; `REGISTRY_CORE_AWE_*`
is ignored there and AWE silently stays off). The chart
points these at the release's own client (`global.authClientId`), which needs
**Service accounts** enabled in Keycloak; check that on each environment. A
missing token fails the ingest with `AWE_BEARER_TOKEN_REQUIRED`.

Notes on the mapping:
- The form stores administrative **codes** without the leading zero (kebele
  `40801101001`). The template pads them to Master Data's ids
  (`kebele-ET040801101001`) and sends `geo_lowest_level_value_id`; the farmer
  service fills region, zone, woreda and kebele names from it. A kebele picked
  as "other" falls back to the woreda.
- Photos (the farmer photo and each parcel's land certificate) arrive from ODK
  Central as file names only. The connector downloads them and inlines them as
  `{"__type": "File", ...}` when the pipeline's `source_config.embed_attachments`
  is true (the default; set `false` to turn it off). Files over
  `attachment_max_bytes` (default 10 MiB) are skipped and the record is sent
  without them. Each file is held in memory while it is encoded. The web user
  the connector signs in as needs read access to the project's submissions.
  After changing `farmer_transform.j2`, re-run db-seed or re-upload it to MinIO
  (`mc cp odk/templates/farmer_transform.j2 myminio/templates/`).
- Every stage writes a JSON-lines **ingestion log** (`odk.ingest`): polls, each attachment
  (embedded, not uploaded, too large, download failed), map/validate/send failures, what the
  registry received, files stored or refused, and each ingest attempt. The connector writes
  `/app/logs/odk-ingest.jsonl` (`CONNECTOR_INGEST_LOG_FILE`, empty for stdout only) and the
  registry worker `logs/odk-ingest.jsonl` (`REGISTRY_EXTENSIONS_ODK_INGEST_LOG_FILE`); both
  also go to stdout. Find a submission with
  `jq 'select(.source_event_id == "<form>:<uuid:...>" or .instance_id == "<uuid:...>")'`.
  The event table is in `docs/odk/FARMER_REGISTRY_ODK_COMPLETE_GUIDE.md`, section 9.1.
- The form asks no crop season; crops default to `MEHER`.
- The submission is validated like a staff entry. A draft that breaks a farmer
  rule (say, digits in a name) stays at `ingestion_status=FAILED` with the rule's
  message in `ingestion_latest_error_code`.
