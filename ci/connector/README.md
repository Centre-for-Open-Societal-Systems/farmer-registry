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
KUBECONFIG=<cluster> ./ci/connector/deploy.sh <image tag>
```

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
`odk/ATI_Farmers_Profile_ODK_Form_v2.xlsx`, attach `odk/KebeleList.csv` and
`odk/PrimaryCoopList.csv` as media, and publish. Note the project id and form id.

**5. Point the pipeline at it.** Either in the connector UI
(`https://connector-farmer-registry.far.openg2p.test`), or by setting these on
the release so the connector seeds the pipeline itself on first start:

| Setting | Example |
| --- | --- |
| `CONNECTOR_ODK_CENTRAL_BASE_URL` | `http://commons-services-odk-central-frontend` |
| `CONNECTOR_ODK_PROJECT_ID` | the project holding the form |
| `CONNECTOR_ODK_FORM_ID` | the published form id |
| `CONNECTOR_ODK_CENTRAL_EMAIL` | an ODK Central account with access to it |
| `CONNECTOR_ODK_CENTRAL_PASSWORD` | mount from a secret, never in values |

Nothing is seeded until all five are set, and no credentials are built in.

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

## Known gap: the registry-side mapping

The connector wraps each submission as `{header: {...}, message: {payload: ...}}`.
The registry's classification in `far` currently matches a DCI-shaped payload —
`$.body.message.search_response[0].data.reg_record_type=>^Farmer$`, with the
record at `search_response[0].data.reg_records[0]` — so a connector submission
reaches `incoming_classified_data` but does not yet become a draft intake.

crop and live close this gap with an `odk_ingest_hooks.py` in their extension
that patches the intake-form data service and the per-register services. The
farmer extension has no equivalent yet, and `odk/templates/farmer_transform.j2`
is not referenced by any database row (crop's `csr_odk_transform.j2` is not
either). Closing it means either adding semantic patterns and a transform
template for the connector's envelope, or porting the hook approach. That work
belongs with whoever owns the farmer extension's ingestion pipeline.
