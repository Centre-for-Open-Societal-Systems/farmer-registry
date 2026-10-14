# ODK form and ingestion code

The documentation is in [`docs/odk/README.md`](../docs/odk/README.md). This
directory holds the form and what runs:

| File | |
| --- | --- |
| `ATI_Farmers_Profile_ODK_Form_v2.xlsx` | the XLSForm published on ODK Central (`farmer_profile`) |
| `media/KebeleList.csv`, `media/PrimaryCoopList.csv` | the CSVs the form reads |
| `build_location_media.py` | rebuilds the form's location lists from the shared hierarchy |
| `templates/farmer_transform.j2` | ODK submission → intake sections (db-seed uploads it to the `templates` bucket) |
| `test_transform.py` | renders the transform on an OData-shaped submission (CI) |
| `setup_farmer_odk_connector.sql` | registry routing for `FARMER_ODK_MODEL`, by hand (db-seed applies `zz_farmer_odk_ingestion.sql`) |
| `seed_connector_pipelines.sql` | a connector pipeline for the form, by hand (fill in the ODK login) |
| `connector-k8s-deployment.yaml` | plain manifests; the deployed connector uses `ci/connector/` |
| `test_odk_central_submission.py`, `live_demo_submit.py` | send a test submission to ODK Central |
