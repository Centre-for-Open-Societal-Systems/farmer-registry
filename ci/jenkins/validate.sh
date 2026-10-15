#!/usr/bin/env bash
set -euo pipefail
python -m pytest -q -p no:cacheprovider test/test_rp_pin_lockstep.py \
  test/test_jenkins_deployment.py test/test_pm_manifest.py \
  test/test_odk_location_media.py test/test_odk_geo_compatibility.py \
  test/test_shared_geo_migration.py farmer-extension/tests/test_metadata_effective_layer.py
python odk/test_transform.py > /tmp/odk-transform.log
bash -n ci/jenkins/deploy-dev.sh
