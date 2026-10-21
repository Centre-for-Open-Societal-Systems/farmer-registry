#!/usr/bin/env bash
set -euo pipefail
python -m pytest -q -p no:cacheprovider tests/unit
python tests/unit/test_odk_transform.py > /tmp/odk-transform.log
bash -n ci/deploy/deploy-dev.sh
bash -n ci/deploy/deploy-rc.sh
bash -n ci/deploy/cutover-dev.sh ci/deploy/cutover-renderer.sh ci/deploy/oan-renderer.sh
bash tests/integration/test-deploy-shell.sh
bash tests/integration/test-staging-deploy-shell.sh
bash tests/integration/test-cutover-shell.sh
bash -n ci/services/run.sh ci/services/run-container.sh
bash -n scripts/operations/connector/fetch-backup-container.sh
bash tests/integration/test-container-shell.sh
bash -n ci/build/staging-legacy.sh ci/deploy/staging-legacy.sh
python ci/environments.py dev
python ci/environments.py staging
python scripts/check-doc-links.py
