#!/usr/bin/env bash
# Run from the reviewed, merged Farmer checkout on the trusted VPN agent.
set -euo pipefail
set +x
umask 077
: "${KUBECONFIG:?Bind farmer-dev-kubeconfig}"
: "${REGISTRY_OUTCOME_FILE:?Sanitized Jenkins artifact destination required}"
: "${IMAGE_TAG:?Built validation image tag required}"
MODE=${1:-upgrade}
case "$MODE" in
  upgrade) : "${CUTOVER_BACKUP_DIRECTORY:?Private restore-verified backup directory required}" ;;
  --rehearse) ;;
  *) echo 'Expected upgrade or --rehearse' >&2; exit 1 ;;
esac
test "${DELIVERY_ENVIRONMENT:-}" = dev
test "${HELM_NAMESPACE:-}" = farmer
test "${HELM_RELEASE:-}" = farmer-registry
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"' EXIT
guard() {
  local mounts=(-v "$PWD:/repo:ro" -v "$STATE:$STATE")
  if [[ "$MODE" == upgrade ]]; then
    mounts+=(-v "$CUTOVER_BACKUP_DIRECTORY:/backup:ro")
  fi
  docker run --rm --network none --user "$(id -u):$(id -g)" \
    -e DELIVERY_ENVIRONMENT -e HELM_NAMESPACE -e HELM_RELEASE \
    "${mounts[@]}" \
    "coss-ci/validation:$IMAGE_TAG" python "${GUARD_SCRIPT:-ci/deploy/cutover.py}" "$@"
}
snapshot() {
  helm status "$HELM_RELEASE" -n farmer -o json > "$STATE/status.json"
  helm get values "$HELM_RELEASE" -n farmer -o json > "$STATE/values.json"
  helm get manifest "$HELM_RELEASE" -n farmer > "$STATE/before.yaml"
  kubectl get jobs -n farmer -o json > "$STATE/jobs.json"
  if [[ "$MODE" == upgrade ]]; then
    guard backup /backup "$STATE/status.json" "$STATE/values.json" "$STATE/before.yaml" "$STATE/jobs.json"
  else
    GUARD_SCRIPT=ci/deploy/deployment.py guard complete "$STATE/status.json"
  fi
}
snapshot
if [[ "$MODE" == upgrade ]]; then
  guard attempt "$STATE/status.json" "$STATE/before.yaml" "$STATE/attempt.json"
  mkdir -p "$(dirname "$REGISTRY_OUTCOME_FILE")"
  cp "$STATE/attempt.json" "$REGISTRY_OUTCOME_FILE"
fi
CHART="$STATE/oan-farmer.tgz"
URL=$(GUARD_SCRIPT=ci/deploy/oan_chart.py guard url)
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --output "$CHART" "$URL"
GUARD_SCRIPT=ci/deploy/oan_chart.py guard verify "$CHART"
guard prepare "$STATE/values.json" "$STATE/before.yaml" "$STATE/values.yaml" "$CHART"
export OAN_CHART_ARCHIVE="$CHART" OAN_VALUES_FILE="$STATE/values.yaml"
helm lint "$CHART" --strict -f "$STATE/values.yaml" > "$STATE/lint.log"
helm template "$HELM_RELEASE" "$CHART" -n farmer -f "$STATE/values.yaml" \
  --is-upgrade --dry-run=server --no-hooks --post-renderer ci/deploy/cutover-renderer.sh > "$STATE/after.yaml"
guard validate "$STATE/before.yaml" "$STATE/after.yaml"
if [[ "$MODE" == --rehearse ]]; then
  helm status "$HELM_RELEASE" -n farmer -o json > "$STATE/current-status.json"
  GUARD_SCRIPT=ci/deploy/deployment.py guard unchanged "$STATE/status.json" "$STATE/current-status.json"
  guard rehearsal "$STATE/status.json" "$STATE/after.yaml" "$STATE/outcome.json"
  mkdir -p "$(dirname "$REGISTRY_OUTCOME_FILE")"
  cp "$STATE/outcome.json" "$REGISTRY_OUTCOME_FILE"
  echo 'PASS: read-only OAN cutover rehearsal; upgrade and operational acceptance remain pending.'
  exit 0
fi
# Re-read backups, release and Jobs immediately before upgrading.
snapshot
helm upgrade "$HELM_RELEASE" "$CHART" -n farmer -f "$STATE/values.yaml" \
  --no-hooks --post-renderer ci/deploy/cutover-renderer.sh --wait --timeout 20m > "$STATE/upgrade.log" 2>&1
helm get manifest "$HELM_RELEASE" -n farmer > "$STATE/deployed.yaml"
guard validate "$STATE/before.yaml" "$STATE/deployed.yaml"
helm list -n farmer --filter '^farmer-registry$' -o json > "$STATE/chart.json"
guard installed "$STATE/chart.json"
helm status "$HELM_RELEASE" -n farmer -o json > "$STATE/final-status.json"
guard outcome "$STATE/final-status.json" "$STATE/deployed.yaml" "$STATE/outcome.json"
mkdir -p "$(dirname "$REGISTRY_OUTCOME_FILE")"
cp "$STATE/outcome.json" "$REGISTRY_OUTCOME_FILE"
echo 'Chart-only upgrade verified. Complete the operational acceptance checks before enabling normal dev builds.'
