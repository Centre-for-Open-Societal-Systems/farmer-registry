#!/usr/bin/env bash
# Build every service target from the repo-root Dockerfile and push it to
# Docker Hub under the given namespace. Mirrors the unified-Dockerfile
# structure docker-compose.yml already builds from (one Dockerfile, one
# target per service) rather than the older per-service docker/*/Dockerfile
# files, which are no longer what gets built.
#
# Usage:
#   ./docker/build-and-push.sh [namespace] [version]
#
# Defaults: namespace=rediet03, version=0.1.0
#
# Requires: `docker login` already done for the target namespace.

set -euo pipefail

NAMESPACE="${1:-rediet03}"
VERSION="${2:-0.1.0}"

cd "$(dirname "$0")/.."

for name in staff-api partner-api celery staff-ui db-seed; do
  image="${NAMESPACE}/farmer-registry:${name}-${VERSION}"
  echo "=== Building ${image} (target: ${name}) ==="
  docker build -f Dockerfile --target "${name}" -t "${image}" .
  echo "=== Pushing ${image} ==="
  docker push "${image}"
done

echo "Done. Pushed:"
for name in staff-api partner-api celery staff-ui db-seed; do
  echo "  ${NAMESPACE}/farmer-registry:${name}-${VERSION}"
done
