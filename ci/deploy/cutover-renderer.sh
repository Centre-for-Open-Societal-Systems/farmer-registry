#!/usr/bin/env bash
set -euo pipefail
set +x
export OAN_CHART_ONLY=true
exec bash ci/deploy/oan-renderer.sh
