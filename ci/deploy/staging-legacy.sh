#!/usr/bin/env bash
# Legacy staging deployment: retain its chart and environment, never install defaults.
set -euo pipefail
set +x
umask 077
: "${KUBECONFIG:?Bind staging-farmer-kubeconfig}"
: "${IMAGE_TAG:?Missing commit tag}"
test "${HELM_NAMESPACE:-}" = far
test "${HELM_RELEASE:-}" = farmer-registry
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"' EXIT
helm repo add openg2p-gitlab https://gitlab.com/api/v4/projects/84460547/packages/helm/stable --force-update
helm repo update openg2p-gitlab
# `update`, not `build`: Chart.lock is gitignored (it pins a
# moving -develop tag, so it buys no determinism), which leaves
# the workspace copy on the agent as the only one -- and git
# never cleans an ignored file between builds. `build` trusts
# that stale lock and refuses the moment Chart.yaml's pin moves:
# "the lock file (Chart.lock) is out of sync with the
# dependencies file (Chart.yaml)", which is exactly what failed
# staging #4 on the .383 -> .384 bump. `update` re-resolves from
# Chart.yaml and rewrites the lock.
helm dependency update ${HELM_CHART_DIR}

cat > $STATE/override.yaml <<EOF
registry:
  staffApi:
    image:
      repository: ${ECR_REGISTRY}/${ECR_REPOSITORY}/staff-api
      tag: "${IMAGE_TAG}"
  staffUi:
    image:
      repository: ${ECR_REGISTRY}/${ECR_REPOSITORY}/staff-ui
      tag: "${IMAGE_TAG}"
  partnerApi:
    image:
      repository: ${ECR_REGISTRY}/${ECR_REPOSITORY}/partner-api
      tag: "${IMAGE_TAG}"
  celeryWorker:
    image:
      repository: ${ECR_REGISTRY}/${ECR_REPOSITORY}/celery
      tag: "${IMAGE_TAG}"
  celeryBeat:
    image:
      repository: ${ECR_REGISTRY}/${ECR_REPOSITORY}/celery
      tag: "${IMAGE_TAG}"
  dbSeed:
    image:
      repository: ${ECR_REGISTRY}/${ECR_REPOSITORY}/db-seed
      tag: "${IMAGE_TAG}"
    loadAttributes: false
  sanity:
    image:
      repository: ${ECR_REGISTRY}/${ECR_REPOSITORY}/sanity-tests
      tag: "${IMAGE_TAG}"
# Of the chart's analytics layer only the reporting views and their hourly
# refresh are deployed: the dashboard API reads fr_rpt_farmer and fr_rpt_land.
# The bulk sample-data generator, the Superset dashboard import and the Insights
# maps content stay out of this deploy.
analytics:
  bulkSample:
    enabled: false
  reportingViews:
    enabled: true
  dashboards:
    enabled: false
mapsContent:
  enabled: false
EOF
# Preserve the existing dashboard API; no dashboard build is attempted.

# Keep the release's own values (hostnames, Keycloak and IAM
# wiring, cookie domain) and change only what this build owns.
# The chart defaults render placeholder *.openg2p.org hosts, so
# upgrading from the CI file alone would reset the live
# environment to them. An existing deployed release is mandatory.
helm status "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o json > "$STATE/status.json"

helm get values "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o yaml > $STATE/values.yaml
docker build -t "coss-ci/validation:$IMAGE_TAG" ci/validation
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/repo:ro" -v "$STATE:$STATE:ro" -v "$STATE/values.yaml:/private-values.yaml:ro" \
  "coss-ci/validation:$IMAGE_TAG" python ci/environments.py staging --status "$STATE/status.json" --values /private-values.yaml

# Never install placeholder defaults after a namespace or credential error.


# Dry-run render of exactly what the upgrade below applies.
helm template ${HELM_RELEASE} ${HELM_CHART_DIR} -n ${HELM_NAMESPACE} \
    -f "$STATE/values.yaml" \
    -f "$STATE/override.yaml" > $STATE/rendered.yaml
echo "Rendered $(wc -l < $STATE/rendered.yaml) lines to $STATE/rendered.yaml"

# Keep Helm output private; hook logs may contain credentials or submitted data.

if ! helm upgrade ${HELM_RELEASE} ${HELM_CHART_DIR} -n ${HELM_NAMESPACE} \
    -f "$STATE/values.yaml" \
    -f "$STATE/override.yaml" --timeout 20m > "$STATE/upgrade.log" 2>&1; then
    echo 'Staging upgrade failed; inspect restricted Helm and hook logs.' >&2
    kubectl get jobs,pods -n "$HELM_NAMESPACE"
    exit 1
fi


kubectl rollout status deployment/${HELM_RELEASE}-staff-portal-api -n ${HELM_NAMESPACE} --timeout=180s
kubectl rollout status deployment/${HELM_RELEASE}-staff-portal-ui -n ${HELM_NAMESPACE} --timeout=180s
kubectl rollout status deployment/${HELM_RELEASE}-partner-api -n ${HELM_NAMESPACE} --timeout=180s
kubectl rollout status deployment/${HELM_RELEASE}-celery-worker -n ${HELM_NAMESPACE} --timeout=180s
kubectl rollout status deployment/${HELM_RELEASE}-celery-beat-producer -n ${HELM_NAMESPACE} --timeout=180s


# explicit log of that outcome
echo "=== db-seed Job outcome ==="
kubectl get job ${HELM_RELEASE}-db-seed -n ${HELM_NAMESPACE} -o jsonpath='{.status.succeeded} succeeded / {.status.failed} failed{"\n"}' || echo "(job not found under this name -- check the actual name with: kubectl get jobs -n ${HELM_NAMESPACE})"
echo "=== sanity Job outcome ==="
kubectl get job ${HELM_RELEASE}-sanity -n ${HELM_NAMESPACE} -o jsonpath='{.status.succeeded} succeeded / {.status.failed} failed{"\n"}' || echo "(job not found under this name -- check the actual name with: kubectl get jobs -n ${HELM_NAMESPACE})"
echo "=== reporting-views Job outcome ==="
kubectl get job ${HELM_RELEASE}-fr-reporting-views -n ${HELM_NAMESPACE} -o jsonpath='{.status.succeeded} succeeded / {.status.failed} failed{"\n"}' || echo "(job not found under this name -- check the actual name with: kubectl get jobs -n ${HELM_NAMESPACE})"
