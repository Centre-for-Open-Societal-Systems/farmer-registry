# Changelog

Notable changes to the Farmer Registry, newest first, in the format of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are the repository version in `init.yaml` (see [release](docs/release.md)). Before this file, the history is
the git log and the pull requests.

## [Unreleased]

### Changed

- Consolidate the Farmer Registry domain into `openg2p_registry_farmer_extension` (G2R-635).
  The staff API, partner API and Celery install that one package on the OpenG2P platform.
  The seed image takes metadata and templates from the package; the sample loader and reporting SQL stay under `docker/db-seed/`.

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
