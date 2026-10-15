# ODK map tiles blocked by referrer policy

Dev is repaired. Public staging still needs its VM configuration updated;
its map is **not accepted** while tile requests omit their Referer.

The screenshot matches an [upstream Central issue](https://github.com/getodk/central/issues/1885).
`Referrer-Policy: same-origin` suppresses the cross-origin Referer required by
the [OSM tile policy](https://operations.osmfoundation.org/policies/tiles/).
A 200 tile response alone is insufficient: old staging also returned 200 in
some automated sessions while omitting its Referer.

| Endpoint | Owner | Outcome |
| --- | --- | --- |
| `https://odk.commons-dev.oanstaging.com` | `commons/commons-services-odk-central-frontend`, Central v2025.2.1 | Repaired; Chrome and Firefox passed |
| `https://odk-central.oanstaging.com` | EC2 `odk-vm-2`, instance `i-032cfc39355e3d39b`, Central v2026.1.2 | Server access needed; API credentials work |
| `odk.commons.staging.openg2p.test` | Internal staging Kubernetes Commons ODK | Does not serve public staging; trial change reverted |

Central application credentials do not grant server access. The public VM's
EC2 key pair is `aws_key`. The available AWS principal cannot use Instance
Connect; the VM is not registered with Systems Manager. IAM and network
permissions were not changed. The [form API](https://docs.getodk.org/central-api-form-management/)
does not expose Nginx or Enketo tile configuration. `webformsEnabled` switches
the whole renderer and is not a map policy patch. The Farmer form has five
Ethiopian-calendar fields and other behavior requiring compatibility testing
before a renderer migration; it remains on Enketo.

## Scoped correction

Use `strict-origin-when-cross-origin` only in the Enketo proxy's headers include.
Tiles receive the site's origin without form IDs, paths or query tokens. Keep
`same-origin` elsewhere, and preserve all cache/security directives, tile URLs,
attribution, TLS, callbacks, images and existing storage.

Dev's [owning Commons values overlay](../../ci/odk/values-map-tiles.yaml)
changes only `odk-central.frontend.setupOdkScript` and `odkConfTemplate`.
Startup generates an Enketo headers file from the pinned image, failing if its
original policy changed. Only the Enketo block includes that file. The live
ConfigMap has these two changes and the frontend Deployment has a checksum
annotation to reload its subPath mounts. The backend and databases were not
restarted, and the image is unchanged.

Merge that overlay into the **owning Commons release values** at its next
reviewed deployment. The scoped live patch does not alter Helm's stored release
records; upgrading Commons without the overlay can remove the fix. Source
delivery remains feature -> develop -> staging. Do not upgrade the failed
staging Commons release just for this repair.

For public staging, inspect the actual Compose files, service names, image
digest, mounts and startup script. Back up and checksum the live template,
headers and Compose configuration in protected storage. Do not copy dev's
older template over the VM's newer configuration. Run the offline helper **on
the VM** against the captured files:

```sh
python3 scripts/operations/prepare-odk-map-policy.py \
  --template /private/before/odk.conf.template \
  --headers /private/before/common-headers.conf \
  --output /private/odk-map-policy
```

The helper never connects or executes Compose. It refuses unknown proxy
blocks, ambiguous policies and existing output directories. Review the two
generated files and checksums. Its Compose overlay assumes a service named
`nginx` and uses absolute read-only bind paths: verify both on the actual host.
Combine it with **all** existing Compose files and settings. Rehearse with the
installed image and existing TLS/dependency mounts; require `nginx -t`. Recreate
only the frontend with `--no-deps --no-build --pull never`, retaining the overlay
in persistent Compose configuration. On failure restore the captured frontend
configuration; never change submissions to recover a map setting.

## Acceptance

Dev passed an isolated startup/syntax check using the exact installed Nginx
image, then authenticated Chrome and Firefox checks of the published form:

- Every visible tile rendered and returned 200. Screenshots show the basemap.
- Observed tile requests sent only `Referer: https://odk.commons-dev.oanstaging.com/`,
  with no cache-bypass headers.
- Enketo returned one `strict-origin-when-cross-origin` policy. Central `/` and
  `/v1/projects` retained `same-origin`.
- Clicking saved a point; no JavaScript errors occurred.
- Version 1.0.5, both dev submissions and the staging submission remain; saved
  submission XML matches the pre-update copies. No submission was created.
- The temporary browser account was deleted and its login rejected. The
  permanent reader still authenticates.

Dev's checksum-verified backup is `/var/backups/farmer-odk-map-20261016/` on the
dev host. Protected operator evidence includes network observations, screenshots
and cleanup results. That directory on the staging Kubernetes host records the
**reverted trial**, not a public-staging repair. No VM backup is claimed yet.

Repeat these checks on public staging after the server repair. Reload old form
tabs to obtain the new document policy. Physical Android Collect and device GPS
remain separate checks; this repair concerns web basemap requests.
