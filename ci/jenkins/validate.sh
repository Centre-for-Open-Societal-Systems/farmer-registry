#!/usr/bin/env bash
set -euo pipefail
python -m pytest -q -p no:cacheprovider test/test_rp_pin_lockstep.py \
  test/test_jenkins_deployment.py test/test_service_coordination.py test/test_awe_worker_token.py test/test_worker_rollout.py test/test_pm_manifest.py \
  test/test_odk_location_media.py test/test_odk_geo_compatibility.py test/test_odk_actor.py test/test_odk_signature.py test/test_signing_rollout.py \
  test/test_shared_geo_migration.py farmer-extension/tests/test_metadata_effective_layer.py
python odk/test_transform.py > /tmp/odk-transform.log
bash -n ci/jenkins/deploy-dev.sh
bash ci/jenkins/test-deploy-shell.sh
bash -n ci/services/run.sh ci/services/run-container.sh
bash -n ci/connector/fetch-backup-container.sh
bash ci/services/test-container-shell.sh
