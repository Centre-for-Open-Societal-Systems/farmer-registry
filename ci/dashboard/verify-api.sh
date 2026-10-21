#!/usr/bin/env bash
set -euo pipefail
source_dir=$(cd "$1" && pwd)
docker run --rm -v "$source_dir:/src:ro" python:3.11-slim sh -ec '
  cp -a /src /work
  cd /work
  pip install --no-cache-dir -r requirements-dev.txt
  ruff check app tests
  ruff format --check app tests
  python -m pytest -q -W error -p no:cacheprovider
'
