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

# Reading an existing release is mandatory; never install placeholder defaults
# after a credential, namespace or context mistake. Private manifests stay local.
helm status "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o json > "$STATE/status.json"
python ci/jenkins/deployment.py status "$STATE/status.json"
helm get values "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o json > "$STATE/values.json"
helm get manifest "$HELM_RELEASE" -n "$HELM_NAMESPACE" > "$STATE/before.yaml"
python ci/jenkins/deployment.py prepare "$STATE/values.json" "$STATE/before.yaml" "$STATE/values.yaml"

# This gate includes all 36 intake/register/history coordinate columns and the
# document-history field. Migrations remain explicit backed-up operator actions.
kubectl exec -i -n farmer deploy/farmer-registry-staff-portal-api -c staff-portal-api -- \
  python3 - < ci/gen2/check_geo_schema.py
helm repo add openg2p https://openg2p.github.io/openg2p-helm --force-update
helm dependency update "$CHART"
helm lint "$CHART" --strict -f "$STATE/values.yaml" > "$STATE/lint.log"
helm template "$HELM_RELEASE" "$CHART" -n "$HELM_NAMESPACE" \
  -f "$STATE/values.yaml" > "$STATE/after.yaml"
python ci/jenkins/deployment.py validate "$STATE/before.yaml" "$STATE/after.yaml"

# The chart's secret lookups run against the cluster during upgrade. Do not
# kubectl-apply the offline template: its generated Secret values are previews.
if ! helm upgrade "$HELM_RELEASE" "$CHART" -n "$HELM_NAMESPACE" \
  -f "$STATE/values.yaml" --atomic --wait --wait-for-jobs --timeout 20m \
  > "$STATE/upgrade.log" 2>&1; then
  echo 'Registry Helm upgrade failed; atomic rollback requested. Inspect Helm history and seed/sanity pod logs with the deployment credentials.' >&2
  # Print status only; manifests and raw seed logs may contain credentials/data.
  helm history "$HELM_RELEASE" -n "$HELM_NAMESPACE" --max 3
  kubectl get jobs,pods -n "$HELM_NAMESPACE"
  exit 1
fi
for component in staff-portal-api partner-api staff-portal-ui celery-worker celery-beat-producer; do
  kubectl rollout status "deployment/$HELM_RELEASE-$component" -n "$HELM_NAMESPACE" --timeout=180s
done
helm get manifest "$HELM_RELEASE" -n "$HELM_NAMESPACE" > "$STATE/deployed.yaml"
printf '\n---\n' >> "$STATE/deployed.yaml"
helm get hooks "$HELM_RELEASE" -n "$HELM_NAMESPACE" >> "$STATE/deployed.yaml"
python ci/jenkins/deployment.py validate "$STATE/before.yaml" "$STATE/deployed.yaml"
kubectl exec -i -n farmer deploy/farmer-registry-staff-portal-api -c staff-portal-api -- \
  python3 - < ci/gen2/check_geo_schema.py
echo "Deployed Registry commit $IMAGE_TAG to farmer; Commons and farmer-connector releases were not upgraded."
