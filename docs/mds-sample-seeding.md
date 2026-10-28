# MDS-owned sample seeding

Shared geography, lists and demographic sample facts originate in the selected
openg2p-data pack, loaded into MDS. Farmer reads MDS through its existing MD_PG
connection. It does not seed geography, carry demographic CSV/JSON snapshots,
or invent titles, grandfather names or agricultural assets. Registry-owned form,
policy and template metadata remain in the extension.

Approved operational records still belong in Farmer. LOAD_SAMPLE_DATA=true
explicitly creates these through native intake, AWE approval and Celery ingestion;
it is not a direct database import or an automatic mirror of MDS. Leave it false
when deploying without demo records. Both Farmer image variants use this loader.

## Deployment sequence

1. Merge the companion openg2p-data change and publish/load ETH-OAN with samples
   enabled. Its 21 people include six household heads with source-owned three-part
   full_name values. Existing two-part samples fail preflight until reloaded.
2. Publish geography and reference lists through MDS/MDM. Configure read access
   with MD_PGHOST, MD_PGDATABASE, MD_PGUSER and MD_PGPASSWORD (and port if needed).
3. Deploy the reviewed Farmer seed image with LOAD_GEO_DATA=false and
   OAN_SAMPLES_FROM_MASTER_DATA=true. Set LOAD_SAMPLE_DATA=true only for the
   explicit demo load. Configure existing staff accounts, IAM permissions and AWE
   assignees first; INTAKE_SEED_PASSWORD must come from a Secret. This loader never
   provisions accounts, resets passwords or changes Keycloak client settings.
4. Verify six households, 21 household members and six farmers through approved,
   processed intakes. The six heads become farmers; not every demographic person
   is a farmer. No farm, crop or livestock facts are present in this sample pack.

Unrelated farmers do not suppress loading. All selected head identities already
registered is a no-op. Any partial/in-flight sample match stops for native intake
recovery; force replay is not supported. Existing records are never deleted.
INTAKE_SEED_MAX_HOUSEHOLDS limits the selected ordered households (default 25).
Sample loading is a single-job operation, not safe for concurrent invocations.

## Verification

Run python -m pytest tests/unit/test_mds_sample_seed.py. HTTP simulation instructions
and limitations are in ../postman/simulations/mds-seed.context.md.
The isolated PostgreSQL contract check tests/integration/check_mds_samples_db.py
requires MDS_SAMPLE_TEST_DSN (database name starting mds_seed_test) and
MDS_SAMPLE_TEST_PACK pointing at the companion ETH-OAN pack. It creates and removes
only its own temporary schema. Native IAM/AWE/Celery acceptance must be checked in
a disposable deployment before promotion; mocks do not establish that acceptance.
