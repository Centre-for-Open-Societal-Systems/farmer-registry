#!/usr/bin/env bash
set -euo pipefail
python -m pytest -q -p no:cacheprovider tests/unit
bash -n ci/deploy/deploy-dev.sh
bash -n ci/deploy/deploy-rc.sh
bash -n ci/deploy/fresh-install-dev.sh ci/deploy/oan-renderer.sh
bash tests/integration/test-deploy-shell.sh
bash tests/integration/test-fresh-install-shell.sh
bash tests/integration/test-staging-deploy-shell.sh
bash -n ci/services/run.sh ci/services/run-container.sh
bash -n scripts/operations/connector/fetch-backup-container.sh
bash tests/integration/test-container-shell.sh
bash -n ci/build/staging-legacy.sh ci/deploy/staging-legacy.sh
python ci/environments.py dev
python ci/environments.py staging
python scripts/check-doc-links.py
