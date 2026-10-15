# ODK form and ingestion code

See the [ODK geography rollout and current dev evidence](../docs/odk-geography-rollout.md).
This directory holds the form and ingestion assets:

| File | |
| --- | --- |
| `ATI_Farmers_Profile_ODK_Form_v2.xlsx` | the XLSForm published on ODK Central (`farmer_profile`) |
| `media/KebeleList.csv`, `media/PrimaryCoopList.csv` | the CSVs the form reads |
| `build_location_media.py` | rebuilds the form's location lists from the shared hierarchy |
| `templates/farmer_transform.j2` | ODK submission → intake sections (db-seed uploads it to the `templates` bucket) |
| `test_transform.py` | renders the transform on an OData-shaped submission (CI) |
| `setup_farmer_odk_connector.sql` | registry routing for `FARMER_ODK_MODEL`, by hand (db-seed applies `zz_farmer_odk_ingestion.sql`) |
| `seed_connector_pipelines.sql` | a connector pipeline for the form, by hand (fill in the ODK login) |
| `connector-k8s-deployment.yaml` | legacy plain manifests, not the current Helm release's source of truth |
| `test_odk_central_submission.py`, `live_demo_submit.py` | send a test submission to ODK Central |

The running dev connector is the separate Helm release `farmer-connector` in
namespace `farmer`, not a Commons Base/Services component. The upstream registry
layout no longer vendors the connector applications or their deployment chart;
that does not remove the independently managed live connector. Do not apply the
legacy manifest as an upgrade or uninstall the existing release.

Regenerate/check location assets from the repository root:

```sh
python odk/build_location_media.py --check
python -m pytest test/test_odk_location_media.py test/test_odk_geo_compatibility.py -q
```

The shared dev catalog was migrated to the checked-in COSS hierarchy on
2026-10-15 after restored-database rehearsal and user approval. The 346 mappable
references were updated; 509 unmappable legacy land references remain preserved
and explicitly flagged. ODK form/media publication, matching transform delivery
and an ODK-to-AWE end-to-end test are still separate rollout steps; they have not
been completed by the catalog migration.
