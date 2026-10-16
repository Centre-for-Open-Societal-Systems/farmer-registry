#!/usr/bin/env bash
set -euo pipefail
test "${DELIVERY_ENVIRONMENT:-dev}" = dev
export DELIVERY_ENVIRONMENT=dev
exec bash ci/deploy/deploy-rc.sh "$@"
