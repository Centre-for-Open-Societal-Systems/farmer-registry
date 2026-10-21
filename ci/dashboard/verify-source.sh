#!/usr/bin/env bash
set -euo pipefail
source_dir=$(cd "$1" && pwd)
docker run --rm -v "$source_dir:/src:ro" node:24-slim sh -ec '
  cp -a /src /work
  cd /work
  npm ci --no-audit --no-fund
  npm run lint
  npm run typecheck
  npm test
'
