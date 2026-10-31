#!/usr/bin/env bash
# Staging: install the pinned OAN Farmer chart in namespace farmer on empty databases.
#
# This is the standard OpenG2P first install of the pinned chart, the staging counterpart of
# fresh-install-dev.sh. It differs in what it must not assume:
#   * there may be no release yet, so the install values are the reviewed environment values
#     of the pinned oan-helm commit (oan-chart-staging.json "values"), never chart defaults;
#   * the images come from the protected rehearsal evidence (digests), not from this build;
#   * the archive target is the host named in the Jenkins file credential bound as
#     BACKUP_TARGET_FILE; nothing about it is written in this repository.
# The legacy release in namespace far and its databases (*_far) are never touched.
#
# BACKUP_TARGET_FILE format: line 1 user@host, line 2 absolute directory, line 3 onward the
# known_hosts entries of that host (host keys are always verified).
#
# Order: values and chart verified, then pg_dump archive written and verified on the target, only
# then uninstall, drop, install. If neither a release nor the databases exist (a true first
# install) there is nothing to dump; if either exists, a verified fresh dump is mandatory.
#
# Two evidence modes (ci/deploy/staging.py "mode"):
#   * first-install: the rehearsal was New Dev and the evidence says the target is empty. The
#     backup credentials are not needed and not used, because the script re-checks in the cluster
#     that neither the release nor any target database exists and refuses to go on if one does.
#   * upgrade (the full rehearsal shape): the backup credentials are mandatory and the verified
#     archive is written before anything is removed, exactly as before.
set -euo pipefail
set +x
umask 077
: "${KUBECONFIG:?Jenkins must bind staging-farmer-kubeconfig}"
: "${IMAGE_TAG:?Missing immutable commit image tag}"
: "${STAGING_EVIDENCE_FILE:?Bind trusted staging rehearsal evidence}"
BACKUP_AVAILABLE=false
if [[ -n "${BACKUP_SSH_KEY:-}" || -n "${BACKUP_TARGET_FILE:-}" ]]; then
  : "${BACKUP_SSH_KEY:?Bind the staging backup SSH key credential together with its target}"
  : "${BACKUP_TARGET_FILE:?Bind the staging backup target credential together with its key}"
  BACKUP_AVAILABLE=true
fi
test "${DELIVERY_ACTION:-}" = fresh-install
test "${DELIVERY_ENVIRONMENT:-staging}" = staging
export DELIVERY_ENVIRONMENT=staging
test "${HELM_NAMESPACE:-}" = farmer
test "${HELM_RELEASE:-}" = farmer-registry

CONTRACT=helm/environments/staging/delivery.yaml
REGISTRY_DB=$(awk '$1 == "registryDatabase:" {print $2}' "$CONTRACT")
IDGEN_DB=$(awk '$1 == "idGeneratorDatabase:" {print $2}' "$CONTRACT")
test -n "$REGISTRY_DB" && test -n "$IDGEN_DB"
case "$REGISTRY_DB" in *_far) echo 'Refusing to touch the legacy far databases.' >&2; exit 1 ;; esac
case "$IDGEN_DB" in *_far) echo 'Refusing to touch the legacy far databases.' >&2; exit 1 ;; esac
export REGISTRY_DB IDGEN_DB
STAMP=$(date -u +%Y%m%d-%H%M%S)
JOB="farmer-fresh-install-$STAMP"
STATE=$(mktemp -d)
cleanup() {
  kubectl delete job -n "$HELM_NAMESPACE" "$JOB" --ignore-not-found --wait=false > /dev/null 2>&1 || true
  rm -rf "$STATE"
}
trap cleanup EXIT

# The backup target comes only from the bound credential, when one is bound.
if [[ "$BACKUP_AVAILABLE" == true ]]; then
  BACKUP_HOST=$(sed -n 1p "$BACKUP_TARGET_FILE")
  BACKUP_DIR=$(sed -n 2p "$BACKUP_TARGET_FILE")
  tail -n +3 "$BACKUP_TARGET_FILE" > "$STATE/known_hosts"
  [[ "$BACKUP_HOST" =~ ^[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+$ ]] || { echo 'Backup target host is not user@host.' >&2; exit 1; }
  [[ "$BACKUP_DIR" =~ ^/[A-Za-z0-9_./-]+$ ]] || { echo 'Backup target directory must be an absolute path.' >&2; exit 1; }
  test -s "$STATE/known_hosts" || { echo 'Backup target host key missing.' >&2; exit 1; }
fi

# Python dependencies live in Docker on the agent; host Helm/kubectl keep the
# existing VPN access. The helper receives no kubeconfig or Docker socket.
guard() {
  docker run --rm --network none --user "$(id -u):$(id -g)" \
    -e ECR_REGISTRY -e IMAGE_TAG -e SOURCE_COMMIT -e OAN_CHART_ARCHIVE -e KUBECONFIG_CREDENTIAL \
    -e DELIVERY_ENVIRONMENT -e DELIVERY_ACTION -e HELM_NAMESPACE -e HELM_RELEASE \
    -v "$STAGING_EVIDENCE_FILE:/staging-evidence.json:ro" -e STAGING_EVIDENCE_FILE=/staging-evidence.json \
    -v "$PWD:/repo:ro" -v "$STATE:$STATE" \
    "coss-ci/validation:$IMAGE_TAG" python "${GUARD_SCRIPT:-ci/deploy/deployment.py}" "$@"
}
remote() {
  ssh -i "$BACKUP_SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="$STATE/known_hosts" -o ConnectTimeout=15 "$BACKUP_HOST" "$@"
}

# 1. Gates: this cluster, this pin, this evidence.
kubectl config view --minify -o json > "$STATE/cluster.json"
GUARD_SCRIPT=ci/deploy/staging.py guard cluster "$STATE/cluster.json"
GUARD_SCRIPT=ci/deploy/oan_chart.py guard require-deployable staging
GUARD_SCRIPT=ci/deploy/staging.py guard verify
MODE=$(GUARD_SCRIPT=ci/deploy/staging.py guard mode)
case "$MODE" in
  first-install | upgrade) ;;
  *) echo 'Unknown staging evidence mode.' >&2; exit 1 ;;
esac
if [[ "$MODE" == upgrade && "$BACKUP_AVAILABLE" != true ]]; then
  echo 'The evidence is not a first-install record: bind the backup SSH key and target credentials.' >&2
  exit 1
fi
guard provenance

# 2. The reviewed environment values of the pinned oan-helm commit, checksum verified.
read -r VALUES_URL VALUES_SHA < <(GUARD_SCRIPT=ci/deploy/oan_chart.py guard values-url staging)
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --output "$STATE/environment-values.yaml" "$VALUES_URL"
test "$(sha256sum "$STATE/environment-values.yaml" | cut -d ' ' -f 1)" = "$VALUES_SHA"
CHART="$STATE/oan-farmer.tgz"
URL=$(GUARD_SCRIPT=ci/deploy/oan_chart.py guard url)
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --output "$CHART" "$URL"
GUARD_SCRIPT=ci/deploy/oan_chart.py guard verify "$CHART"
export OAN_CHART_ARCHIVE="$CHART"
: > "$STATE/empty.yaml"
guard prepare-fresh "$STATE/environment-values.yaml" "$STATE/empty.yaml" "$STATE/values.yaml"
helm lint "$CHART" --strict -f "$STATE/values.yaml" > "$STATE/lint.log"
export OAN_VALUES_FILE="$STATE/values.yaml" OAN_CHART_ONLY=false
helm template "$HELM_RELEASE" "$CHART" -n "$HELM_NAMESPACE" -f "$STATE/values.yaml" \
  --post-renderer ci/deploy/oan-renderer.sh > "$STATE/after.yaml"
guard validate-fresh "$STATE/empty.yaml" "$STATE/after.yaml"
if [[ -n "${REGISTRY_OUTCOME_FILE:-}" ]]; then
  guard attempt "$STATE/attempt.json"
  mkdir -p "$(dirname "$REGISTRY_OUTCOME_FILE")"
  cp "$STATE/attempt.json" "$REGISTRY_OUTCOME_FILE"
fi

# 3. Archive both databases. The Jenkins account is confined to the farmer namespace, which holds
#    a copy of the Commons PostgreSQL Secret, so the dump runs in a Job there and is copied out and
#    shipped to the backup target. A database that does not exist yet is recorded as absent.
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
                if [ "\$(psql -X -d postgres -tAc "select 1 from pg_database where datname='\$db'")" = 1 ]; then
                  pg_dump -Fc -d "\$db" -f "\$db.dump"
                  pg_restore --list "\$db.dump" > /dev/null
                  sha256sum "./\$db.dump" >> SHA256SUMS
                else
                  echo absent > "\$db.absent"
                fi
              done
              touch SHA256SUMS READY
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
kubectl cp -n "$HELM_NAMESPACE" "$POD:/tmp/SHA256SUMS" "$STATE/backup/SHA256SUMS" > /dev/null
DUMPED=()
for db in "$REGISTRY_DB" "$IDGEN_DB"; do
  if grep -q "  ./$db.dump\$" "$STATE/backup/SHA256SUMS"; then
    kubectl cp -n "$HELM_NAMESPACE" "$POD:/tmp/$db.dump" "$STATE/backup/$db.dump" > /dev/null
    DUMPED+=("$db.dump")
  fi
done
RELEASE_PRESENT=false
if helm status "$HELM_RELEASE" -n "$HELM_NAMESPACE" -o json > "$STATE/status.json" 2> /dev/null; then
  RELEASE_PRESENT=true
fi
# A first-install record vouches for an empty target only. It is checked here against the cluster,
# before anything is shipped or removed, so it can never authorize replacing existing data.
if [[ "$MODE" == first-install && ( ${#DUMPED[@]} -gt 0 || "$RELEASE_PRESENT" == true ) ]]; then
  echo 'First-install evidence, but a release or a target database already exists; nothing was changed. Use the full rehearsal evidence with the backup credentials.' >&2
  exit 1
fi
if [[ ${#DUMPED[@]} -gt 0 ]]; then
  # The copy must match the checksums taken next to the database.
  (cd "$STATE/backup" && sha256sum -c SHA256SUMS > /dev/null)
  remote "install -d -m 700 $BACKUP_DIR"
  for name in "${DUMPED[@]}" SHA256SUMS; do
    expected=$(sha256sum "$STATE/backup/$name" | cut -d ' ' -f 1)
    written=$(remote "tee $BACKUP_DIR/$STAMP-$name | sha256sum" < "$STATE/backup/$name" | cut -d ' ' -f 1)
    if [[ "$written" != "$expected" ]]; then
      echo "Archive $name did not arrive intact on the backup target; nothing was changed." >&2
      exit 1
    fi
  done
  echo "Archived ${DUMPED[*]} to $BACKUP_HOST:$BACKUP_DIR/$STAMP-*"
fi

# 4. A fresh dump is mandatory whenever anything exists to lose: a release in the namespace or
#    a database. Only a true first install proceeds without one.
if [[ ${#DUMPED[@]} -eq 0 && "$RELEASE_PRESENT" == true ]]; then
  echo 'A release exists but no database could be archived; refusing to continue.' >&2
  exit 1
fi
if [[ ${#DUMPED[@]} -eq 0 ]]; then
  echo "First install: neither release nor databases exist, nothing to archive; the backup credentials are not used (evidence mode $MODE)."
fi

# 5. Remove the release, then the databases. Only now is anything destroyed.
if [[ "$RELEASE_PRESENT" == true ]]; then
  helm uninstall "$HELM_RELEASE" -n "$HELM_NAMESPACE" --wait --timeout 15m
fi
kubectl exec -n "$HELM_NAMESPACE" "$POD" -- psql -X -v ON_ERROR_STOP=1 -d postgres \
  -c "DROP DATABASE IF EXISTS \"$REGISTRY_DB\" WITH (FORCE);" \
  -c "DROP DATABASE IF EXISTS \"$IDGEN_DB\" WITH (FORCE);"
kubectl exec -n "$HELM_NAMESPACE" "$POD" -- touch /tmp/DONE
echo "Dropped $REGISTRY_DB and $IDGEN_DB."

# 6. A first install of the pinned chart: postgres-init creates the databases, the applications
#    migrate them on start, the post-install hooks seed and smoke-test them.
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
echo "Installed Registry into $HELM_NAMESPACE on empty databases."
