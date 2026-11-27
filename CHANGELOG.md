# Changelog

Notable changes to the Farmer Registry, newest first, in the format of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are the repository version in `init.yaml` (see [release](docs/release.md)). Before this file, the history is
the git log and the pull requests.

## [Unreleased]

### Changed

- OpenG2P's Farmer extension is a dependency instead of a copy in the OAN package (G2R-635). The OAN layer is its
  own distribution, `openg2p-registry-oan-farmer-extension` (module `openg2p_registry_oan_farmer_extension`, the
  images' `REGISTRY_EXTENSION_MODULE`). The staff-api, partner-api and celery images build
  `openg2p-registry-farmer-extension` as a wheel from OpenG2P/farmer-registry `19597f7c`, the commit whose
  `farmer-extension/` is `sample-farmer-extension/` and the 1.0.3 code the copy held, so no table, column or
  behaviour changes. Upstream's 1.2 Farmer extension is not taken here: it moves and removes farmer and household
  columns.

### Added

- Guard tests for contracts between files that nothing checks at runtime (#342, #343, #344):
  - base model columns match the platform pin;
  - every seed INSERT has ON CONFLICT;
  - consent scope ids are releasable by the DCI search response;
  - `search_text` is built from real columns;
  - AWE policy keys join across the registry and AWE seeds.
- Coverage report of `farmer-extension/src` in `ci/validation/validate.sh`, with no minimum yet (#345).
- `ci/README.md`: where each check runs (#345).
- `docs/deployment.md`, `docs/release.md` and this changelog.

### Known issues

- The sanity consent scopes in `helm/openg2p-farmer-registry/values.yaml` (`registry.sanity.dataScopes` and
  `deniedScopes`) are not releasable at the pinned platform. They are listed in `test/unit/test_consent_scopes.py`.
