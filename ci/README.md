# CI

What checks a change to this repository, and where each check runs. How to run the suites by hand is in
[docs/testing](../docs/testing/README.md); the delivery itself is in [dev delivery](../docs/dev-farmer-first.md) and
[operations](../docs/operations/README.md).

## Where checks run

| Runner | Trigger | What it runs |
| --- | --- | --- |
| GitHub Actions, [`checks.yml`](../.github/workflows/checks.yml) | every push and pull request | `contracts`: ruff syntax check, `ci/validation/validate.sh`, the staff UI platform commit, the ODK signature client against the Postman simulation. `chart`: Helm dependency build, lint and render. |
| GitHub Actions, [`build.yml`](../.github/workflows/build.yml) | pull requests, pushes to `develop` and `deploy/**` | Builds every image without pushing. In the built images: entry points load the extension, `farmer-extension/tests`, native metadata replay, worker registration and ODK save/rollback. |
| Jenkins, [`Jenkinsfile`](../Jenkinsfile) | one multibranch job | `staging` branch: [`pipelines/staging.groovy`](pipelines/staging.groovy). Everything else, including pull requests: [`pipelines/dev.groovy`](pipelines/dev.groovy). Both start with `validate.sh` in the [validation image](validation/Dockerfile). Only `develop` goes on to publish and deploy. Neither deploys until every GitHub check of the commit is green ([`deploy/require-green-checks.sh`](deploy/require-green-checks.sh)). |
| Jenkins, [`Jenkinsfile.operator`](../Jenkinsfile.operator) | started by hand only | Operator actions such as fresh install ([`pipelines/operator.groovy`](pipelines/operator.groovy)). |

## validation/validate.sh

The offline gate, the same on GitHub and in Jenkins. It needs no cloud credentials, and Jenkins mounts the
repository read-only. In order:

1. `pytest test/unit`, with a coverage report (below).
2. Syntax checks (`bash -n`) and shell harnesses (`test/integration/test-*-shell.sh`) for the deploy, fresh-install,
   staging and services scripts.
3. `ci/environments.py` for dev, staging and staging-legacy.
4. `scripts/check_doc_links.py`: local links in `README.md`, `farmer-extension/README.md` and `docs/`.

Its Python dependencies are [`validation/requirements.txt`](validation/requirements.txt).

### Guard tests

Some unit tests guard contracts between files that nothing checks at runtime. A break there fails silently in a
deployment, so the test names what broke:

| Test | Guards |
| --- | --- |
| `test_metadata_consistency.py` | The column list of the platform's base models matches the platform pin in `docker/*/Dockerfile`. |
| `test_seed_on_conflict.py` | Every INSERT in `meta_data/` and `awe_meta_data/` has ON CONFLICT, so the db-seed can replay. |
| `test_consent_scopes.py` | Every consent scope id named in the repository is a top-level key of the DCI search response. Known invalid ids are listed in the test. |
| `test_search_text.py` | `search_text` is built only from real columns, and raw register INSERTs write it. |
| `test_awe_policy_keys.py` | Registry approval bindings, AWE policies, stages and approver rules join on `policy_key`. |

### Coverage

`validate.sh` reports line coverage of `farmer-extension/src` from `test/unit`, and enforces no minimum. A minimum is
to be agreed. The baseline on 2026-11-23 was 12% of 4,553 statements, on Python 3.12 in the validation image.

The figure is low because most of the extension needs the platform packages and runs only in the image checks of
`build.yml`. That job runs `farmer-extension/tests`, which `validate.sh` does not.

## Folders

| Folder | Contents |
| --- | --- |
| `build/` | Image builds (`images.sh`) and the platform commit check |
| `deploy/` | Dev and staging deploy, fresh install, chart packaging and image naming |
| `services/` | Coordinated Commons service charts |
| `dashboard/` | Dashboard API and source verification |
| `odk/` | Commons ODK values overlays (not Farmer Registry values) |
| `pipelines/` | The Jenkins pipelines the `Jenkinsfile`s load |
| `validation/` | `validate.sh`, its image and requirements, and the image-level checks used by `build.yml` |
| `upstream/` | An example caller of the OpenG2P packaging workflow (not active) |
