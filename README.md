# Farmer Registry

COSS Farmer Registry extends OpenG2P Registry with farmer, household, land, crop,
livestock, membership and intake metadata. Dev uses platform **1.2.2-rc.544**;
staging retains its separately managed legacy platform.

Start with the [documentation index](docs/README.md).

| Directory | Purpose |
| --- | --- |
| farmer-extension/ | Installable farmer domain package and seed metadata |
| docker/ | Application images and build-time platform patches |
| helm/ | Owning charts and explicit dev/staging configuration |
| integrations/registry-connector/ | Upstream connector runtime adapters |
| ci/ | Environment pipelines, build, validation and deployment helpers |
| scripts/operations/ | Backup, migration, identity and recovery commands |
| tests/ | Unit, runtime, integration, end-to-end and performance suites |
| local/ | Isolated local development stack |
| odk/ | XLSForm, media, mapping and legacy integration assets |
| docs/ | Guides, operations and historical evidence |

For local verification:

```sh
python -m pip install -r ci/validation/requirements.txt
python -m pytest
```

See [testing](docs/testing/README.md), [local development](docs/development/local-stack.md),
and [delivery](docs/operations/README.md) for complete workflows.
