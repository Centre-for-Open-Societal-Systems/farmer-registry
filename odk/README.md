# ODK ingestion code

The form, its media and the documentation are in [`docs/odk/`](../docs/odk/README.md).
This directory holds what runs:

| File | |
| --- | --- |
| `templates/farmer_transform.j2` | ODK submission → intake sections (db-seed uploads it to the `templates` bucket) |
| `test_transform.py` | renders the transform on an OData-shaped submission (CI) |
| `setup_farmer_odk_connector.sql` | registry routing for `FARMER_ODK_MODEL`, by hand (db-seed applies `zz_farmer_odk_ingestion.sql`) |
| `seed_connector_pipelines.sql` | a connector pipeline for the form, by hand (fill in the ODK login) |
| `connector-k8s-deployment.yaml` | plain manifests; the deployed connector uses `ci/connector/` |
| `test_odk_central_submission.py`, `live_demo_submit.py` | send a test submission to ODK Central |
