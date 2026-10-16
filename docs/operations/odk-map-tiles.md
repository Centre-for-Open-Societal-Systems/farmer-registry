# ODK map tiles blocked by referrer policy

Dev and public staging are repaired. Both pass authenticated Chrome and Firefox
checks of rendered tiles, origin-only Referer headers and point selection.

The screenshot matches an [upstream Central issue](https://github.com/getodk/central/issues/1885).
`Referrer-Policy: same-origin` suppresses the cross-origin Referer required by
the [OSM tile policy](https://operations.osmfoundation.org/policies/tiles/).
A 200 tile response alone is insufficient: old staging also returned 200 in
some automated sessions while omitting its Referer.

| Endpoint | Owner | Outcome |
| --- | --- | --- |
| `https://odk.commons-dev.oanstaging.com` | `commons/commons-services-odk-central-frontend`, Central v2025.2.1 | Repaired; Chrome and Firefox passed |
| `https://odk-central.oanstaging.com` | EC2 `odk-vm-2`, instance `i-032cfc39355e3d39b`, Central v2026.1.2 | Repaired; Chrome and Firefox passed |
| `odk.commons.staging.openg2p.test` | Internal staging Kubernetes Commons ODK | Does not serve public staging; trial change reverted |

The existing Jenkins `backend-ssh-key` credential, used through `vpn-agent2`,
matches the VM's authorized SSH key. Its host key was verified against the EC2
console's fingerprint before access. No new SSH key, IAM or network permission
was needed. The [form API](https://docs.getodk.org/central-api-form-management/)
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

For another installation still using the old policy, inspect its Compose files, service names, image
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

## Public staging execution

The VM's owning `/opt/central/docker-compose.yml` now adds one read-only bind
mount for `/opt/central/files/nginx/enketo-headers.conf`. Its mounted
`files/nginx/odk.conf.template` changes only the Enketo block's headers include.
Every other header, route, cache setting, environment variable, TLS volume and
Compose service configuration was preserved.

The candidate passed startup generation and `nginx -t` in a disposable container
using the exact installed image and existing volumes mounted read-only. It
published no ports; the rehearsal replaced the Certbot/background-server branch
with the syntax check, so it requested no certificates. Only Nginx was recreated
for the live apply, with `--no-deps --no-build --pull never`. Its image stayed
`sha256:836a820b8381c7551691b735aedb158f2ca3bbd63d4a68482fdd2dee29cf0854`.
All existing mount sources, including anonymous TLS/DH volumes, were preserved.
The seven other running containers retained their IDs and start times. Nginx
became healthy and its live syntax check passed.

Nine original configuration/inspection files are checksum verified under
`/var/backups/farmer-odk-map-20261016-vm/` on the ODK VM. A protected second
archive was verified in the operator workspace. That directory contains the
candidate, rehearsal, apply and public-browser acceptance evidence. For recovery,
first check for changes made after this repair, then restore only the captured
Compose file and Nginx template and recreate only Nginx with its retained image.
Keep existing volumes; never restore application data for this header repair.

## Acceptance

Both environments passed isolated startup/syntax checks using their installed
Nginx images, then authenticated Chrome and Firefox checks of the published form:

- Every visible tile rendered and returned 200. Screenshots show the basemap.
- Observed tile requests sent only their environment's site origin as Referer,
  with no cache-bypass headers: `https://odk.commons-dev.oanstaging.com/` in dev
  and `https://odk-central.oanstaging.com/` in staging.
- Enketo returned one `strict-origin-when-cross-origin` policy. Central `/` and
  `/v1/projects` retained `same-origin`.
- Clicking saved a point; no JavaScript errors occurred.
- Version 1.0.5, both dev submissions and the staging submission remain; saved
  submission XML matches the pre-update copies. Staging's attachment was also
  compared byte for byte after the VM repair. No submission was created.
- The temporary browser account was deleted and its login rejected. The
  permanent reader still authenticates.

Dev's checksum-verified backup is `/var/backups/farmer-odk-map-20261016/` on the
dev host. Protected operator evidence includes network observations, screenshots
and cleanup results. That directory on the staging Kubernetes host records the
**reverted trial**, separate from the successful public-staging VM repair above.

Repeat these checks after subsequent Nginx upgrades. Reload old form
tabs to obtain the new document policy. Physical Android Collect and device GPS
remain separate checks; this repair concerns web basemap requests.
