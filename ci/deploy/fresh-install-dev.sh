#!/usr/bin/env bash
# Dev only: rebuild the Farmer registry from an empty database.
#
# This is the standard OpenG2P first install of the pinned chart, done again:
# the release is uninstalled, the registry and ID-generator databases are
# dropped, and `helm install` runs postgres-init, the application migrations
# and the post-install seed on empty databases, exactly as a first install
# would. Secrets the chart marks `resource-policy: keep` (database passwords,
# Keycloak client secrets, the AWE callback HMAC) survive the uninstall, and
# postgres-init re-syncs the database roles to them. Commons, the connector and
# the dashboard releases are not touched.
#
# Every farmer, household, document, approval and issued ID on dev is lost.
# Both databases are archived to the dev box first, over the existing
# backup key, and the archive is checked before anything is removed.
set -euo pipefail
set +x
umask 077
: "${KUBECONFIG:?Jenkins must bind farmer-dev-kubeconfig}"
: "${ECR_REGISTRY:?Missing published ECR registry}"
: "${IMAGE_TAG:?Missing immutable commit image tag}"
: "${BACKUP_SSH_KEY:?Bind farmer-new-dev-backup-ssh}"
test "${DELIVERY_ACTION:-}" = fresh-install
test "${DELIVERY_ENVIRONMENT:-dev}" = dev
export DELIVERY_ENVIRONMENT=dev
test "${HELM_NAMESPACE:-}" = farmer
test "${HELM_RELEASE:-}" = farmer-registry

CONTRACT=helm/environments/dev/delivery.yaml
REGISTRY_DB=$(awk '$1 == "registryDatabase:" {print $2}' "$CONTRACT")
IDGEN_DB=$(awk '$1 == "idGeneratorDatabase:" {print $2}' "$CONTRACT")
test -n "$REGISTRY_DB" && test -n "$IDGEN_DB"
export REGISTRY_DB IDGEN_DB
BACKUP_HOST=ubuntu@13.201.58.55
BACKUP_DIR=/var/backups/oan/farmer
KNOWN_HOSTS=scripts/operations/connector/dev-known-hosts
STAMP=$(date -u +%Y%m%d-%H%M%S)
JOB="farmer-fresh-install-$STAMP"
STATE=$(mktemp -d)
cleanup() {
  kubectl delete job -n "$HELM_NAMESPACE" "$JOB" --ignore-not-found --wait=false > /dev/null 2>&1 || true
  rm -rf "$STATE"
}
trap cleanup EXIT

# Python dependencies live in Docker on the agent; host Helm/kubectl keep the
# existing VPN access. The helper receives no kubeconfig or Docker socket.
guard() {
  docker run --rm --network none --user "$(id -u):$(id -g)" \
    -e ECR_REGISTRY -e IMAGE_TAG -e SOURCE_COMMIT -e OAN_CHART_ARCHIVE \
    -e DELIVERY_ENVIRONMENT -e HELM_NAMESPACE -e HELM_RELEASE \
    -v "$PWD:/repo:ro" -v "$STATE:$STATE" \
    "coss-ci/validation:$IMAGE_TAG" python "${GUARD_SCRIPT:-ci/deploy/deployment.py}" "$@"
}
remote() {
  ssh -i "$BACKUP_SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="$KNOWN_HOSTS" -o ConnectTimeout=15 "$BACKUP_HOST" "$@"
}

GUARD_SCRIPT=ci/deploy/oan_chart.py guard require-deployable dev

# 1. The live release supplies the install values: the same chart, the same
#    environment values, this build's images. Nothing is installed from chart
#    defaults.
helm status "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o json > "$STATE/status.json"
guard status "$STATE/status.json"
helm get values "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o json > "$STATE/values.json"
helm get manifest "$HELM_RELEASE" -n "$HELM_NAMESPACE" > "$STATE/before.yaml"
printf '\n---\n' >> "$STATE/before.yaml"
helm get hooks "$HELM_RELEASE" -n "$HELM_NAMESPACE" >> "$STATE/before.yaml"
if [[ -n "${REGISTRY_OUTCOME_FILE:-}" ]]; then
  guard provenance
fi
CHART="$STATE/oan-farmer.tgz"
URL=$(GUARD_SCRIPT=ci/deploy/oan_chart.py guard url)
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --output "$CHART" "$URL"
GUARD_SCRIPT=ci/deploy/oan_chart.py guard verify "$CHART"
export OAN_CHART_ARCHIVE="$CHART"
guard prepare "$STATE/values.json" "$STATE/before.yaml" "$STATE/values.yaml"
helm lint "$CHART" --strict -f "$STATE/values.yaml" > "$STATE/lint.log"
export OAN_VALUES_FILE="$STATE/values.yaml" OAN_CHART_ONLY=false
helm template "$HELM_RELEASE" "$CHART" -n "$HELM_NAMESPACE" -f "$STATE/values.yaml" \
  --post-renderer ci/deploy/oan-renderer.sh > "$STATE/after.yaml"

# 2. Archive both databases. The Jenkins account is confined to the farmer
#    namespace, which holds a copy of the Commons PostgreSQL Secret, so the
#    dump runs in a Job there and is copied out and shipped to the dev box.
kubectl get secret -n "$HELM_NAMESPACE" commons-postgresql -o name > /dev/null
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: $JOB
  namespace: $HELM_NAMESPACE
  labels:
    app.kubernetes.io/name: farmer-fresh-install
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 3600
  template:
    metadata:
      labels:
        app.kubernetes.io/name: farmer-fresh-install
    spec:
      restartPolicy: Never
      containers:
        - name: postgres
          image: docker.io/openg2p/postgresql:16.4.0-debian-12-r14
          env:
            - name: PGHOST
              value: commons-postgresql.commons.svc.cluster.local
            - name: PGUSER
              value: postgres
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef:
                  name: commons-postgresql
                  key: postgres-password
            - name: REGISTRY_DB
              value: "$REGISTRY_DB"
            - name: IDGEN_DB
              value: "$IDGEN_DB"
          command: ["bash", "-c"]
          args:
            - |
              set -euo pipefail
              cd /tmp
              for db in "\$REGISTRY_DB" "\$IDGEN_DB"; do
                pg_dump -Fc -d "\$db" -f "\$db.dump"
                pg_restore --list "\$db.dump" > /dev/null
              done
              sha256sum ./*.dump > SHA256SUMS
              touch READY
              # Stay up until the archive is copied out and the databases are dropped.
              while [ ! -f DONE ]; do sleep 5; done
EOF
kubectl wait -n "$HELM_NAMESPACE" --for=condition=Ready pod -l "job-name=$JOB" --timeout=300s > /dev/null
POD=$(kubectl get pod -n "$HELM_NAMESPACE" -l "job-name=$JOB" -o name | head -n 1)
POD=${POD#pod/}
test -n "$POD"
for _ in $(seq 1 120); do
  if kubectl exec -n "$HELM_NAMESPACE" "$POD" -- test -f /tmp/READY 2> /dev/null; then break; fi
  if [[ "$(kubectl get pod -n "$HELM_NAMESPACE" "$POD" -o jsonpath='{.status.phase}')" == Failed ]]; then
    echo 'Database archive failed; nothing was changed.' >&2
    exit 1
  fi
  sleep 5
done
kubectl exec -n "$HELM_NAMESPACE" "$POD" -- test -f /tmp/READY
mkdir -p "$STATE/backup"
for name in "$REGISTRY_DB.dump" "$IDGEN_DB.dump" SHA256SUMS; do
  kubectl cp -n "$HELM_NAMESPACE" "$POD:/tmp/$name" "$STATE/backup/$name" > /dev/null
done
(cd "$STATE/backup" && sha256sum -c SHA256SUMS > /dev/null)
remote "sudo -n install -d -m 700 -o root -g root $BACKUP_DIR"
for name in "$REGISTRY_DB.dump" "$IDGEN_DB.dump" SHA256SUMS; do
  expected=$(sha256sum "$STATE/backup/$name" | cut -d ' ' -f 1)
  written=$(remote "sudo -n tee $BACKUP_DIR/$STAMP-$name | sha256sum" < "$STATE/backup/$name" | cut -d ' ' -f 1)
  if [[ "$written" != "$expected" ]]; then
    echo "Archive $name did not arrive intact on the dev box; nothing was changed." >&2
    exit 1
  fi
done
echo "Archived $REGISTRY_DB and $IDGEN_DB to $BACKUP_HOST:$BACKUP_DIR/$STAMP-*"

# 3. Remove the release, then the databases. Only now is anything destroyed.
helm uninstall "$HELM_RELEASE" -n "$HELM_NAMESPACE" --wait --timeout 15m
kubectl exec -n "$HELM_NAMESPACE" "$POD" -- psql -X -v ON_ERROR_STOP=1 -d postgres \
  -c "DROP DATABASE IF EXISTS \"$REGISTRY_DB\" WITH (FORCE);" \
  -c "DROP DATABASE IF EXISTS \"$IDGEN_DB\" WITH (FORCE);"
kubectl exec -n "$HELM_NAMESPACE" "$POD" -- touch /tmp/DONE
echo "Dropped $REGISTRY_DB and $IDGEN_DB."

# 4. A first install of the pinned chart: postgres-init creates the databases,
#    the applications migrate them on start, the post-install hooks seed and
#    smoke-test them.
if ! helm install "$HELM_RELEASE" "$CHART" -n "$HELM_NAMESPACE" -f "$STATE/values.yaml" \
  --wait --wait-for-jobs --timeout 30m --post-renderer ci/deploy/oan-renderer.sh \
  > "$STATE/install.log" 2>&1; then
  echo 'Registry Helm install failed. Inspect Helm history and seed/sanity pod logs with the deployment credentials.' >&2
  guard diagnose "$STATE/install.log" || echo 'Could not classify the private Helm error log.' >&2
  helm history "$HELM_RELEASE" -n "$HELM_NAMESPACE" --max 3 || true
  kubectl get jobs,pods -n "$HELM_NAMESPACE" || true
  exit 1
fi
helm status "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o json > "$STATE/final-status.json"
guard complete "$STATE/final-status.json"
for component in staff-portal-api partner-api staff-portal-ui celery-worker celery-beat-producer; do
  kubectl rollout status "deployment/$HELM_RELEASE-$component" -n "$HELM_NAMESPACE" --timeout=180s
done
kubectl exec -i -n "$HELM_NAMESPACE" deploy/farmer-registry-staff-portal-api -c staff-portal-api -- \
  python3 - < scripts/operations/commons/check_geo_schema.py
# The seed applies metadata with ON_ERROR_STOP=0; fail the delivery if OAN's checks do not hold.
CHECKS=farmer-extension/src/openg2p_registry_farmer_extension/meta_data/zz-oan/90_checks.sql
python3 scripts/operations/commons/check_seed_metadata.py "$CHECKS" > "$STATE/check_seed_metadata.py"
kubectl exec -i -n "$HELM_NAMESPACE" deploy/farmer-registry-staff-portal-api -c staff-portal-api -- python3 - < "$STATE/check_seed_metadata.py"

# The partner API's DCI response-signing public key (chart dciSigning hook), for
# the consuming registries' chart values; the private key never leaves the Secret.
if kubectl get configmap "$HELM_RELEASE-dci-signing-public" -n "$HELM_NAMESPACE" > /dev/null 2>&1; then
  echo "DCI response-signing public key (kid $(kubectl get configmap "$HELM_RELEASE-dci-signing-public" -n "$HELM_NAMESPACE" -o go-template='{{index .data "kid"}}')):"
  kubectl get configmap "$HELM_RELEASE-dci-signing-public" -n "$HELM_NAMESPACE" -o go-template='{{index .data "public-key.pem"}}'
  echo
fi
if [[ -n "${REGISTRY_OUTCOME_FILE:-}" ]]; then
  guard outcome "$STATE/final-status.json" "$STATE/outcome.json"
  mkdir -p "$(dirname "$REGISTRY_OUTCOME_FILE")"
  cp "$STATE/outcome.json" "$REGISTRY_OUTCOME_FILE"
fi
echo "Installed Registry into $HELM_NAMESPACE on empty databases; archive: $BACKUP_HOST:$BACKUP_DIR/$STAMP-*"
