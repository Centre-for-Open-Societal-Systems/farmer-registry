#!/usr/bin/env bash
set -euo pipefail
# Coverage is reported, not enforced: no minimum until one is agreed (ci/README.md). Jenkins mounts the
# repository read-only, so the data file goes to the temporary directory.
COVERAGE_FILE="${TMPDIR:-/tmp}/farmer-registry.coverage" python -m pytest -q -p no:cacheprovider test/unit \
  --cov=farmer-extension/src --cov-report=term:skip-covered
bash -n ci/deploy/deploy-dev.sh
bash -n ci/deploy/deploy-rc.sh
bash -n ci/deploy/fresh-install-dev.sh ci/deploy/fresh-install-staging.sh ci/deploy/oan-renderer.sh
bash test/integration/test-deploy-shell.sh
bash test/integration/test-fresh-install-shell.sh
bash test/integration/test-fresh-install-staging-shell.sh
bash test/integration/test-staging-deploy-shell.sh
bash -n ci/services/run.sh ci/services/run-container.sh
bash -n scripts/operations/connector/fetch-backup-container.sh
bash test/integration/test-container-shell.sh
bash -n ci/build/staging-legacy.sh ci/deploy/staging-legacy.sh
python ci/environments.py dev
python ci/environments.py staging
python ci/environments.py staging-legacy
python scripts/check_doc_links.py
