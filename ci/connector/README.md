# farmer-registry-connector release (New Dev)

The New Dev `farmer-registry-connector` release (namespace `farmer`) is defined here.

| File | What it is |
| --- | --- |
| `chart/` | The `openg2p-connector` 0.1.0 chart, vendored from `OpenG2P/registry-connector` at `bc565efd47c1` (`api/deploy/charts/openg2p-connector`, the commit the running images were built from) with the signing overlay of `scripts/operations/connector/chart_signing.py` applied (`cossSigning`, `cossQueue`). |
| `farmer-connector.values.yaml` | The release's user values (`helm get values`, revision 11) with the four images replaced by this repository's connector images, pinned by digest. No secret values. |
| `upgrade-farmer-connector.sh` | Plan or upgrade, run by Jenkins `DELIVERY_ACTION=connector-plan` / `connector-upgrade`. |

Run `connector-plan` first: it prints the rendered manifest diff against the running release
and a server-side dry run, and changes nothing. `connector-upgrade` archives the connector
database `farmer_connector_v2` to the dev box, repeats the plan, runs
`helm upgrade --reset-values -f farmer-connector.values.yaml`, checks images and signing env,
and verifies the admin-only API: a request without a token must be 401/403 and one with a
`registry-connector` client-credentials token must succeed.

The Secrets `farmer-connector-v2-db` and `farmer-connector-v2-signing` belong to the
`farmer-connector-credentials` release and are not touched. The legacy VirtualService
`legacy-farmer-registry-connector` is outside this release. Connector definitions, checkpoints
and webhook secrets live in the connector database.

Rollback: `helm rollback farmer-registry-connector 11 -n farmer`.
