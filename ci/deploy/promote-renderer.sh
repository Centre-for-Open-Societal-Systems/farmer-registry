#!/usr/bin/env bash
# Helm post-renderer of a promotion: the corrections of oan_compat.py, with the values of OAN_PROMOTED_VALUES.
set -euo pipefail
set +x
: "${IMAGE_TAG:?Validation image required}"
: "${OAN_PROMOTED_VALUES:?Promoted values required}"
exec docker run --rm -i --network none --user "$(id -u):$(id -g)" \
  -e DELIVERY_ENVIRONMENT -e HELM_NAMESPACE -e HELM_RELEASE -e OAN_PROMOTED_VALUES \
  -v "$PWD:/repo:ro" "oan-ci/validation:$IMAGE_TAG" python ci/deploy/oan_compat.py
