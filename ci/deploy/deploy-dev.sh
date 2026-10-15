#!/usr/bin/env bash
# Upgrade only an existing new-dev Registry release. No Commons/connector writes.
set -euo pipefail
set +x
umask 077
: "${KUBECONFIG:?Jenkins must bind farmer-dev-kubeconfig}"
: "${ECR_REGISTRY:?Missing published ECR registry}"
: "${IMAGE_TAG:?Missing immutable commit image tag}"
test "${HELM_RELEASE:-}" = farmer-registry
test "${HELM_NAMESPACE:-}" = farmer
CHART=helm/openg2p-farmer-registry
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"' EXIT

# Python dependencies live in Docker on both agents; host Helm/kubectl keep the
# existing VPN access. The helper receives no kubeconfig or Docker socket.
guard() {
  # Bash 4.3 + nounset cannot expand an empty array. Keep this nonempty.
  local evidence_args=(-e APPLY_COMMONS_IDENTITY)
  if [[ "${APPLY_COMMONS_IDENTITY:-false}" == true ]]; then
    : "${IDENTITY_EVIDENCE_FILE:?Bind fresh identity readiness evidence}"
    evidence_args+=(-v "$IDENTITY_EVIDENCE_FILE:/identity-evidence.json:ro" -e IDENTITY_EVIDENCE_FILE=/identity-evidence.json)
  fi
  docker run --rm --network none --user "$(id -u):$(id -g)" \
    -e ECR_REGISTRY -e IMAGE_TAG -e SOURCE_COMMIT "${evidence_args[@]}" \
    -v "$PWD:/repo:ro" -v "$STATE:$STATE" \
    "coss-ci/validation:$IMAGE_TAG" python ci/deploy/deployment.py "$@"
}

# Reading an existing release is mandatory; never install placeholder defaults
# after a credential, namespace or context mistake. Private manifests stay local.
if [[ -n "${REGISTRY_OUTCOME_FILE:-}" ]]; then
  guard provenance
fi
helm status "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o json > "$STATE/status.json"
guard status "$STATE/status.json"
MODE=$(guard upgrade-mode "$STATE/status.json")
UPGRADE_FLAGS=(--wait --wait-for-jobs --timeout 20m)
if [[ "$MODE" == normal ]]; then
  UPGRADE_FLAGS+=(--atomic)
else
  echo 'Recovering a failed release with all preflight gates. Automatic rollback is disabled to avoid restoring an older successful revision.'
fi
helm get values "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o json > "$STATE/values.json"
helm get manifest "$HELM_RELEASE" -n "$HELM_NAMESPACE" > "$STATE/before.yaml"
guard prepare "$STATE/values.json" "$STATE/before.yaml" "$STATE/values.yaml"

# This gate includes all 36 intake/register/history coordinate columns and the
# document-history field. Migrations remain explicit backed-up operator actions.
kubectl exec -i -n farmer deploy/farmer-registry-staff-portal-api -c staff-portal-api -- \
  python3 - < scripts/operations/commons/check_geo_schema.py
helm repo add openg2p https://openg2p.github.io/openg2p-helm --force-update
helm dependency build "$CHART"
helm lint "$CHART" --strict -f "$STATE/values.yaml" > "$STATE/lint.log"
helm template "$HELM_RELEASE" "$CHART" -n "$HELM_NAMESPACE" \
  -f "$STATE/values.yaml" > "$STATE/after.yaml"
guard validate "$STATE/before.yaml" "$STATE/after.yaml"

# Another operator may have changed the release while images/chart were checked.
helm status "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o json > "$STATE/current-status.json"
guard unchanged "$STATE/status.json" "$STATE/current-status.json"

# The chart's secret lookups run against the cluster during upgrade. Do not
# kubectl-apply the offline template: its generated Secret values are previews.
if ! helm upgrade "$HELM_RELEASE" "$CHART" -n "$HELM_NAMESPACE" \
  -f "$STATE/values.yaml" "${UPGRADE_FLAGS[@]}" \
  > "$STATE/upgrade.log" 2>&1; then
  echo "Registry Helm upgrade failed (mode: $MODE). Inspect Helm history and seed/sanity pod logs with the deployment credentials." >&2
  guard diagnose "$STATE/upgrade.log" || echo 'Could not classify the private Helm error log.' >&2
  # Print status only; manifests and raw seed logs may contain credentials/data.
  helm history "$HELM_RELEASE" -n "$HELM_NAMESPACE" --max 3 || true
  kubectl get jobs,pods -n "$HELM_NAMESPACE" || true
  exit 1
fi
helm status "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o json > "$STATE/final-status.json"
guard complete "$STATE/final-status.json"
for component in staff-portal-api partner-api staff-portal-ui celery-worker celery-beat-producer; do
  kubectl rollout status "deployment/$HELM_RELEASE-$component" -n "$HELM_NAMESPACE" --timeout=180s
done
helm get manifest "$HELM_RELEASE" -n "$HELM_NAMESPACE" > "$STATE/deployed.yaml"
printf '\n---\n' >> "$STATE/deployed.yaml"
helm get hooks "$HELM_RELEASE" -n "$HELM_NAMESPACE" >> "$STATE/deployed.yaml"
guard validate "$STATE/before.yaml" "$STATE/deployed.yaml"
kubectl exec -i -n farmer deploy/farmer-registry-staff-portal-api -c staff-portal-api -- \
  python3 - < scripts/operations/commons/check_geo_schema.py
if [[ -n "${REGISTRY_OUTCOME_FILE:-}" ]]; then
  guard outcome "$STATE/final-status.json" "$STATE/outcome.json"
  mkdir -p "$(dirname "$REGISTRY_OUTCOME_FILE")"
  cp "$STATE/outcome.json" "$REGISTRY_OUTCOME_FILE"
fi
echo "Deployed Registry commit $IMAGE_TAG to farmer; shared and optional releases are coordinated separately."
