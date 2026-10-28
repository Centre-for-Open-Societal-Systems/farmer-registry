# Testing

All test code lives under `tests/`. Root `pytest.ini` selects the offline unit
suite by default; runtime and live suites require explicit commands.

```sh
python -m pip install -r ci/validation/requirements.txt
python -m pytest
bash ci/validation/validate.sh
```

The Bash entrypoint also checks deployment shell behavior and the ODK transform.
It runs unchanged in the Jenkins validation image without cloud credentials.
Helm-specific tests skip when Helm is unavailable.

The 2026-10-16 staging implementation was verified locally on Windows. In this
restricted session Python's mode-0700 temporary directories were unreadable.
The local pytest launcher used inherited directory ACLs only for disposable,
synthetic test fixtures. Production backup modes were unchanged. Linux shell,
Helm, container runtime and database restore checks still require their normal
CI or trusted-host environments; the Windows unit result does not establish them.

| Suite | Location | Environment |
| --- | --- | --- |
| Offline guards/metadata | `test/unit/` | Python dependencies; Helm for chart cases |
| Deployment shell harnesses | `test/integration/` | Bash, including Bash 4.3 compatibility |
| Database integration | `test/integration/test_data_scopes.py` | Platform packages, disposable PostgreSQL |
| Worker and signing | `test/runtime/` | Built worker/Partner API images |
| Domain behavior | `test/runtime/extension/` | Built staff API image |
| Connector media/signing | `test/runtime/test_connector_media.py` | Built connector image |
| Sanity suite | `test/sanity/` | The sanity-tests image against a deployed release |
| Load testing | `performance-testing/` | Explicit target, authorization and seeded data |

Dev image builds run worker attribution and Partner API signature checks. The
connector coordinator runs media/signing tests and isolated database rehearsal
before publication. The sanity image overlays Farmer-specific tests on the
upstream harness.

Example domain runtime check using an already built image:

```sh
docker run --rm -v "$PWD:/repo:ro" -e PYTHONPATH=/repo/farmer-extension/src \
  -w /repo/test/runtime --entrypoint python "$STAFF_API_IMAGE" -m unittest \
  extension.test_domain_validation_utils extension.test_farmer_geo_sync \
  extension.test_intake_record_image_urls extension.test_household_family_size
```

Never run live intake, approval or load scripts as unit-test checks. Historical
load results do not establish current capacity. See [performance testing](../../performance-testing/README.md).

