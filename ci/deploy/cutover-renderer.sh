#!/usr/bin/env bash
set -euo pipefail
set +x
: "${IMAGE_TAG:?Validation image required}"
exec docker run --rm -i --network none --user "$(id -u):$(id -g)" \
  -e DELIVERY_ENVIRONMENT -e HELM_NAMESPACE -e HELM_RELEASE \
  -v "$PWD:/repo:ro" "coss-ci/validation:$IMAGE_TAG" python ci/deploy/cutover.py filter
