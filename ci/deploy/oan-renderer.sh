#!/usr/bin/env bash
set -euo pipefail
set +x
: "${IMAGE_TAG:?Validation image required}"
: "${OAN_CHART_ARCHIVE:?Verified chart required}"
: "${OAN_VALUES_FILE:?Prepared private values required}"
test "$(dirname "$OAN_CHART_ARCHIVE")" = "$(dirname "$OAN_VALUES_FILE")"
exec docker run --rm -i --network none --user "$(id -u):$(id -g)" \
  -e DELIVERY_ENVIRONMENT -e HELM_NAMESPACE -e HELM_RELEASE \
  -e OAN_CHART_ARCHIVE -e OAN_VALUES_FILE -e OAN_CHART_ONLY \
  -v "$PWD:/repo:ro" -v "$(dirname "$OAN_VALUES_FILE"):$(dirname "$OAN_VALUES_FILE"):ro" \
  "coss-ci/validation:$IMAGE_TAG" python ci/deploy/oan_compat.py
