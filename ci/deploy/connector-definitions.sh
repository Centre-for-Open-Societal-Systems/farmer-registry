#!/usr/bin/env bash
# Apply the declared Farmer connector definitions (helm/environments/<env>/farmer-connector-definitions.yaml)
# with the farmer-connector-definitions release. Runs after the services deploy, on the deploy agent, with the
# environment's kubeconfig in KUBECONFIG. The hook Job runs the image of the running connector API, so a paused
# connector (no API replicas) is skipped: there is nothing to apply the rows to.
#
#   bash ci/deploy/connector-definitions.sh dev|staging
set -euo pipefail
environment=${1:?Expected dev or staging}
case "$environment" in dev|staging) ;; *) echo "Unknown environment: $environment" >&2; exit 2 ;; esac
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
namespace=farmer
values="helm/environments/$environment/farmer-connector-definitions.yaml"
test -f "$values"

replicas=$(kubectl -n "$namespace" get deployment farmer-registry-connector-api -o jsonpath='{.status.readyReplicas}')
if [[ -z "$replicas" || "$replicas" == 0 ]]; then
  echo "[connector-definitions] SKIPPED: farmer-registry-connector-api has no ready replica"
  exit 0
fi
image=$(kubectl -n "$namespace" get deployment farmer-registry-connector-api -o jsonpath='{.spec.template.spec.containers[0].image}')
test -n "$image"

helm upgrade --install farmer-connector-definitions helm/farmer-connector-definitions -n "$namespace" \
  -f "$values" --set-string "image=$image" --atomic --wait --timeout 20m
echo "[connector-definitions] applied $values with $image"
