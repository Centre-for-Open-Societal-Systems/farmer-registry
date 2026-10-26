#!/usr/bin/env bash
# Shared RC upgrade for explicit environment/namespace pairs. No schema writes.
set -euo pipefail
set +x
umask 077
: "${KUBECONFIG:?Jenkins must bind farmer-dev-kubeconfig}"
: "${ECR_REGISTRY:?Missing published ECR registry}"
: "${IMAGE_TAG:?Missing immutable commit image tag}"
DELIVERY_ENVIRONMENT=${DELIVERY_ENVIRONMENT:-dev}
export DELIVERY_ENVIRONMENT
case "$DELIVERY_ENVIRONMENT:${HELM_NAMESPACE:-}" in
  dev:farmer) ;;
  staging:far) : "${STAGING_EVIDENCE_FILE:?Bind trusted staging rehearsal evidence}" ;;
  *) echo 'Invalid deployment environment/namespace pair' >&2; exit 1 ;;
esac
test "${HELM_RELEASE:-}" = farmer-registry
CHART=helm/openg2p-farmer-registry
STATE=$(mktemp -d)
SCHEMA_JOB=''
cleanup() {
  if [[ -n "$SCHEMA_JOB" ]]; then
    kubectl delete -n far "$SCHEMA_JOB" --ignore-not-found --wait=false >/dev/null 2>&1 || true
  fi
  rm -rf "$STATE"
}
trap cleanup EXIT

# Python dependencies live in Docker on both agents; host Helm/kubectl keep the
# existing VPN access. The helper receives no kubeconfig or Docker socket.
guard() {
  # Bash 4.3 + nounset cannot expand an empty array. Keep this nonempty.
  local evidence_args=(-e APPLY_COMMONS_IDENTITY -e DELIVERY_ENVIRONMENT -e KUBECONFIG_CREDENTIAL -e HELM_NAMESPACE -e HELM_RELEASE)
  if [[ "$DELIVERY_ENVIRONMENT" == staging ]]; then
    evidence_args+=(-v "$STAGING_EVIDENCE_FILE:/staging-evidence.json:ro" -e STAGING_EVIDENCE_FILE=/staging-evidence.json)
  fi
  if [[ "${APPLY_COMMONS_IDENTITY:-false}" == true ]]; then
    : "${IDENTITY_EVIDENCE_FILE:?Bind fresh identity readiness evidence}"
    evidence_args+=(-v "$IDENTITY_EVIDENCE_FILE:/identity-evidence.json:ro" -e IDENTITY_EVIDENCE_FILE=/identity-evidence.json)
  fi
  docker run --rm --network none --user "$(id -u):$(id -g)" \
    -e ECR_REGISTRY -e IMAGE_TAG -e SOURCE_COMMIT -e OAN_CHART_ARCHIVE "${evidence_args[@]}" \
    -v "$PWD:/repo:ro" -v "$STATE:$STATE" \
    "coss-ci/validation:$IMAGE_TAG" python "${GUARD_SCRIPT:-ci/deploy/deployment.py}" "$@"
}

if [[ "$DELIVERY_ENVIRONMENT" == dev ]]; then
  GUARD_SCRIPT=ci/deploy/oan_chart.py guard require-deployable dev
  NEW_DEV_RESET_ACTION=check bash ci/deploy/new-dev-reset.sh
fi

if [[ "$DELIVERY_ENVIRONMENT" == staging ]]; then
  kubectl config view --minify -o json > "$STATE/cluster.json"
  GUARD_SCRIPT=ci/deploy/staging.py guard cluster "$STATE/cluster.json"
fi

# Reading an existing release is mandatory; never install placeholder defaults
# after a credential, namespace or context mistake. Private manifests stay local.
if [[ -n "${REGISTRY_OUTCOME_FILE:-}" ]]; then
  guard provenance
  if [[ "$DELIVERY_ENVIRONMENT" == dev ]]; then
    guard attempt "$STATE/attempt.json"
    mkdir -p "$(dirname "$REGISTRY_OUTCOME_FILE")"
    cp "$STATE/attempt.json" "$REGISTRY_OUTCOME_FILE"
  fi
fi
helm status "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o json > "$STATE/status.json"
guard status "$STATE/status.json"
if [[ "$DELIVERY_ENVIRONMENT" == dev ]]; then
  helm list -n "$HELM_NAMESPACE" --filter '^farmer-registry$' -o json > "$STATE/chart.json"
  # Application updates start only after the separate chart-only cutover.
  GUARD_SCRIPT=ci/deploy/cutover.py guard adopted "$STATE/chart.json"
fi
MODE=$(guard upgrade-mode "$STATE/status.json")
UPGRADE_FLAGS=(--wait --wait-for-jobs --timeout 20m)
if [[ "$MODE" == normal && "$DELIVERY_ENVIRONMENT" == dev ]]; then
  UPGRADE_FLAGS+=(--atomic)
elif [[ "$MODE" != normal ]]; then
  echo 'Recovering a failed release with all preflight gates. Automatic rollback is disabled to avoid restoring an older successful revision.'
else
  echo 'Staging promotion keeps automatic Helm rollback disabled across schema migrations.'
fi
helm get values "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o json > "$STATE/values.json"
helm get manifest "$HELM_RELEASE" -n "$HELM_NAMESPACE" > "$STATE/before.yaml"
if [[ "$DELIVERY_ENVIRONMENT" == dev ]]; then
  # Helm stores hook ConfigMaps separately. Include their existing identities
  # rather than treating them as unreviewed new persistent resources.
  printf '\n---\n' >> "$STATE/before.yaml"
  helm get hooks "$HELM_RELEASE" -n "$HELM_NAMESPACE" >> "$STATE/before.yaml"
fi
if [[ "$DELIVERY_ENVIRONMENT" == staging ]]; then
  GUARD_SCRIPT=ci/deploy/staging.py guard cutover "$STATE/status.json" "$STATE/values.json" "$STATE/before.yaml"
fi
if [[ "$DELIVERY_ENVIRONMENT" == dev ]]; then
  CHART="$STATE/oan-farmer.tgz"
  URL=$(GUARD_SCRIPT=ci/deploy/oan_chart.py guard url)
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
    --output "$CHART" "$URL"
  GUARD_SCRIPT=ci/deploy/oan_chart.py guard verify "$CHART"
  export OAN_CHART_ARCHIVE="$CHART"
fi
guard prepare "$STATE/values.json" "$STATE/before.yaml" "$STATE/values.yaml"

# This gate includes all 36 intake/register/history coordinate columns and the
# document-history field. Migrations remain explicit backed-up operator actions.
check_schema() {
  if [[ "$DELIVERY_ENVIRONMENT" == staging ]]; then
    kubectl get deployment farmer-registry-staff-portal-api -n far -o json > "$STATE/api.json"
    guard schema-probe "$STATE/api.json" "$STATE/schema-probe.json"
    SCHEMA_JOB=$(kubectl create -f "$STATE/schema-probe.json" -o name)
    if ! kubectl wait -n far --for=condition=complete "$SCHEMA_JOB" --timeout=100s > "$STATE/schema-wait.log" 2>&1; then
      echo 'Staging schema probe failed; maintenance must remain active.' >&2
      return 1
    fi
    kubectl logs -n far "$SCHEMA_JOB" > "$STATE/schema.log"
    cat "$STATE/schema.log"
    kubectl delete -n far "$SCHEMA_JOB" --wait=true > /dev/null
    SCHEMA_JOB=''
  else
    kubectl exec -i -n "$HELM_NAMESPACE" deploy/farmer-registry-staff-portal-api -c staff-portal-api -- \
      python3 - < scripts/operations/commons/check_geo_schema.py
  fi
}
check_schema
if [[ "$DELIVERY_ENVIRONMENT" == staging ]]; then
  helm repo add openg2p https://openg2p.github.io/openg2p-helm --force-update
  helm dependency build "$CHART"
fi
helm lint "$CHART" --strict -f "$STATE/values.yaml" > "$STATE/lint.log"
RENDER_FLAGS=(--is-upgrade --dry-run=server)
if [[ "$DELIVERY_ENVIRONMENT" == dev ]]; then
  export OAN_VALUES_FILE="$STATE/values.yaml" OAN_CHART_ONLY=false
  RENDER_FLAGS+=(--post-renderer ci/deploy/oan-renderer.sh)
  UPGRADE_FLAGS+=(--post-renderer ci/deploy/oan-renderer.sh)
fi
helm template "$HELM_RELEASE" "$CHART" -n "$HELM_NAMESPACE" \
  -f "$STATE/values.yaml" "${RENDER_FLAGS[@]}" > "$STATE/after.yaml"
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
if [[ "$DELIVERY_ENVIRONMENT" == dev ]]; then
  helm list -n "$HELM_NAMESPACE" --filter '^farmer-registry$' -o json > "$STATE/chart.json"
  GUARD_SCRIPT=ci/deploy/cutover.py guard installed "$STATE/chart.json"
fi
for component in staff-portal-api partner-api staff-portal-ui celery-worker celery-beat-producer; do
  kubectl rollout status "deployment/$HELM_RELEASE-$component" -n "$HELM_NAMESPACE" --timeout=180s
done
helm get manifest "$HELM_RELEASE" -n "$HELM_NAMESPACE" > "$STATE/deployed.yaml"
printf '\n---\n' >> "$STATE/deployed.yaml"
helm get hooks "$HELM_RELEASE" -n "$HELM_NAMESPACE" >> "$STATE/deployed.yaml"
guard validate "$STATE/before.yaml" "$STATE/deployed.yaml"
check_schema
if [[ -n "${REGISTRY_OUTCOME_FILE:-}" ]]; then
  guard outcome "$STATE/final-status.json" "$STATE/outcome.json"
  mkdir -p "$(dirname "$REGISTRY_OUTCOME_FILE")"
  cp "$STATE/outcome.json" "$REGISTRY_OUTCOME_FILE"
fi
echo "Deployed Registry to $HELM_NAMESPACE; shared and optional releases are coordinated separately."
