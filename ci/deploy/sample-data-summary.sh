#!/usr/bin/env bash
# Print the sample loader's SUMMARY line (docker/db-seed/load_sample_data.py) after a delivery with LOAD_SAMPLE_DATA=true.
# The loader always exits 0 so that sample data never fails the registry upgrade; this step is how the pipeline still shows
# "SUCCESS, but only 0 of 21 loaded". It exits 1 when the summary is missing or not OK, and the pipeline turns that into
# UNSTABLE. Read-only: kubectl get and logs on the hook Job helm left in place (delete policy before-hook-creation).
set -euo pipefail
if [ "${LOAD_SAMPLE_DATA:-false}" != true ]; then
  echo "sample data: LOAD_SAMPLE_DATA is off for this delivery, nothing to report"
  exit 0
fi
: "${HELM_NAMESPACE:?}" "${HELM_RELEASE:?}"
job="${HELM_RELEASE}-sample-data-loader"
if ! kubectl -n "$HELM_NAMESPACE" get job "$job" > /dev/null 2>&1; then
  echo "sample data: no Job $job in $HELM_NAMESPACE, so the loader did not run in this delivery"
  exit 1
fi
line=$(kubectl -n "$HELM_NAMESPACE" logs "job/$job" --tail=200 2>/dev/null | grep -F '[load-sample-data] SUMMARY:' | tail -1 || true)
if [ -z "$line" ]; then
  echo "sample data: Job $job printed no SUMMARY line; its last lines:"
  kubectl -n "$HELM_NAMESPACE" logs "job/$job" --tail=15 2>/dev/null || true
  exit 1
fi
echo "sample data: ${line#\[load-sample-data\] }"
case "$line" in
  "[load-sample-data] SUMMARY: OK"*) exit 0 ;;
  *) exit 1 ;;
esac
