#!/usr/bin/env bash
# Upgrade the New Dev farmer-registry-connector release so that it equals git:
# chart ci/connector/chart, values ci/connector/farmer-connector.values.yaml,
# installed with --reset-values (nothing carried over from earlier hand runs).
#
# Upgrade only. The connector database is archived to the New Dev box first
# (same key and host as fresh-install), then a server-side dry run and the
# rendered manifest diff against the running release are printed, and only then
# is the release upgraded. The registry release (farmer-registry), connector
# definitions, checkpoints and webhook secrets are not touched: they live in the
# connector database, which an upgrade does not migrate away.
#
# The connector API is admin-only: the verification mints a client-credentials token for the
# Keycloak client registry-connector (secret from commons/registry-connector) and also asserts
# that a request without a token is refused.
#
# PLAN_ONLY=1 (Jenkins connector-plan) stops after step 3: it changes nothing,
# needs no backup key, and prints the manifest diff and the dry-run result.
#
# Env: KUBECONFIG (farmer-dev-kubeconfig), BACKUP_SSH_KEY (farmer-new-dev-backup-ssh,
# not needed with PLAN_ONLY=1).
set -euo pipefail
set +x
umask 077

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
: "${KUBECONFIG:?Jenkins must bind farmer-dev-kubeconfig}"
: "${PLAN_ONLY:=0}"
[[ "$PLAN_ONLY" == 1 ]] || : "${BACKUP_SSH_KEY:?Bind farmer-new-dev-backup-ssh}"
NAMESPACE=farmer
RELEASE=farmer-registry-connector
CHART=ci/connector/chart
VALUES=ci/connector/farmer-connector.values.yaml
CONNECTOR_DB="${CONNECTOR_DB:-farmer_connector_v2}"
BACKUP_HOST=ubuntu@13.201.58.55
BACKUP_DIR=/var/backups/oan/farmer
KNOWN_HOSTS=scripts/operations/connector/dev-known-hosts
STAMP=$(date -u +%Y%m%d-%H%M%S)
JOB="farmer-registry-connector-backup-$STAMP"
STATE=$(mktemp -d)
cleanup() {
  kubectl delete job -n "$NAMESPACE" "$JOB" --ignore-not-found --wait=false > /dev/null 2>&1 || true
  rm -rf "$STATE"
}
trap cleanup EXIT
remote() {
  ssh -i "$BACKUP_SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="$KNOWN_HOSTS" -o ConnectTimeout=15 "$BACKUP_HOST" "$@"
}

# 1. The release must exist, be deployed, and come from the same chart.
# helm list, not helm status: the deploy node's helm prints no chart in status JSON.
status=$(helm list -n "$NAMESPACE" --filter "^${RELEASE}\$" -o json | python3 -c 'import json,sys; r=json.load(sys.stdin); print(" ".join((r[0]["status"], r[0]["chart"])) if r else "missing")')
echo "Current release: $RELEASE ($status)"
test "$status" = "deployed openg2p-connector-0.1.0"
helm history "$RELEASE" -n "$NAMESPACE" --max 5
kubectl get secret -n "$NAMESPACE" commons-postgresql -o name > /dev/null

plan() {
  helm lint "$CHART" -f "$VALUES"
  helm get manifest "$RELEASE" -n "$NAMESPACE" > "$STATE/current.yaml"
  helm template "$RELEASE" "$CHART" -n "$NAMESPACE" -f "$VALUES" > "$STATE/target.yaml"
  echo "=== manifest diff (running release -> git) ==="
  diff -u "$STATE/current.yaml" "$STATE/target.yaml" || true
  echo "=== end of diff ==="
  helm upgrade "$RELEASE" "$CHART" -n "$NAMESPACE" --reset-values -f "$VALUES" --dry-run=server > /dev/null
  echo "Server-side dry run passed."
}
if [[ "$PLAN_ONLY" == 1 ]]; then
  plan
  echo "PLAN_ONLY: nothing was changed."
  exit 0
fi
remote true

# 2. Archive the connector database (definitions, checkpoints, secrets live here).
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: $JOB
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/name: farmer-registry-connector-backup
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 3600
  template:
    metadata:
      labels:
        app.kubernetes.io/name: farmer-registry-connector-backup
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
            - name: CONNECTOR_DB
              value: "$CONNECTOR_DB"
          command: ["bash", "-c"]
          args:
            - |
              set -euo pipefail
              cd /tmp
              pg_dump -Fc -d "\$CONNECTOR_DB" -f "\$CONNECTOR_DB.dump"
              pg_restore --list "\$CONNECTOR_DB.dump" > /dev/null
              sha256sum ./*.dump > SHA256SUMS
              touch READY
              while [ ! -f DONE ]; do sleep 5; done
EOF
kubectl wait -n "$NAMESPACE" --for=condition=Ready pod -l "job-name=$JOB" --timeout=300s > /dev/null
POD=$(kubectl get pod -n "$NAMESPACE" -l "job-name=$JOB" -o name | head -n 1)
POD=${POD#pod/}
test -n "$POD"
for _ in $(seq 1 120); do
  if kubectl exec -n "$NAMESPACE" "$POD" -- test -f /tmp/READY 2> /dev/null; then break; fi
  if [[ "$(kubectl get pod -n "$NAMESPACE" "$POD" -o jsonpath='{.status.phase}')" == Failed ]]; then
    echo 'Connector database archive failed; nothing was changed.' >&2
    exit 1
  fi
  sleep 5
done
kubectl exec -n "$NAMESPACE" "$POD" -- test -f /tmp/READY
mkdir -p "$STATE/backup"
for name in "$CONNECTOR_DB.dump" SHA256SUMS; do
  kubectl cp -n "$NAMESPACE" "$POD:/tmp/$name" "$STATE/backup/$name" > /dev/null
done
(cd "$STATE/backup" && sha256sum -c SHA256SUMS > /dev/null)
kubectl exec -n "$NAMESPACE" "$POD" -- touch /tmp/DONE
remote "sudo -n install -d -m 700 -o root -g root $BACKUP_DIR"
for name in "$CONNECTOR_DB.dump" SHA256SUMS; do
  expected=$(sha256sum "$STATE/backup/$name" | cut -d ' ' -f 1)
  written=$(remote "sudo -n tee $BACKUP_DIR/$STAMP-connector-$name | sha256sum" < "$STATE/backup/$name" | cut -d ' ' -f 1)
  if [[ "$written" != "$expected" ]]; then
    echo "Archive $name did not arrive intact on the New Dev box; nothing was changed." >&2
    exit 1
  fi
done
echo "Archived $CONNECTOR_DB to $BACKUP_HOST:$BACKUP_DIR/$STAMP-connector-*"

# 3. Show what changes: rendered manifest diff and a server-side dry run.
plan

# 4. Upgrade.
helm upgrade "$RELEASE" "$CHART" -n "$NAMESPACE" --reset-values -f "$VALUES" --wait --timeout 10m
for d in api worker beat ui; do
  kubectl rollout status -n "$NAMESPACE" "deployment/$RELEASE-$d" --timeout=300s
done

# 5. Verify the running pods equal git and the API answers.
want=$(helm get values "$RELEASE" -n "$NAMESPACE" -o json | python3 -c 'import json,sys; v=json.load(sys.stdin); print(" ".join(v[k]["image"]["repository"]+":"+v[k]["image"]["tag"] for k in ("api","ui")))')
want_api=${want%% *}
want_ui=${want##* }
for d in api worker beat ui; do
  got=$(kubectl get deployment -n "$NAMESPACE" "$RELEASE-$d" -o jsonpath='{.spec.template.spec.containers[0].image}')
  expected=$want_api
  [[ "$d" == ui ]] && expected=$want_ui
  test "$got" = "$expected" || { echo "$RELEASE-$d runs $got, expected $expected" >&2; exit 1; }
done
for d in api worker beat; do
  names=$(kubectl get deployment -n "$NAMESPACE" "$RELEASE-$d" -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}{"
"}{end}')
  for n in CONNECTOR_SIGNING_ISSUER CONNECTOR_SIGNING_KEY_ID CONNECTOR_SIGNING_PRIVATE_KEY_PEM; do
    grep -qx "$n" <<< "$names" || { echo "$RELEASE-$d lacks $n" >&2; exit 1; }
  done
done
API_POD=$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/instance=$RELEASE,app.kubernetes.io/component=api -o name | head -n 1)
# The connector API is admin-only (Keycloak realm staff, client registry-connector, role
# REGISTRY_CONNECTOR_ADMIN). Mint a client-credentials token for the client's service account.
# The client secret is read from the Secret registry-connector in commons (key client_secret,
# written by keycloak-init). Neither the secret nor the token is printed or put on a command line:
# the token reaches the pod on stdin.
KEYCLOAK_URL="${KEYCLOAK_URL:-https://keycloak-development.oanstaging.com}"
TOKEN_URL="${KEYCLOAK_URL%/}/realms/staff/protocol/openid-connect/token"
set +x
client_secret=$(kubectl get secret registry-connector -n commons -o jsonpath='{.data.client_secret}' | base64 -d)
[[ -n "$client_secret" ]] || { echo "Secret commons/registry-connector has no client_secret; cannot verify the admin-only API." >&2; exit 1; }
ADMIN_TOKEN=$(CLIENT_SECRET="$client_secret" TOKEN_URL="$TOKEN_URL" python3 -c '
import json, os, sys, urllib.error, urllib.parse, urllib.request
body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": "registry-connector",
                               "client_secret": os.environ["CLIENT_SECRET"]}).encode()
try:
    with urllib.request.urlopen(urllib.request.Request(os.environ["TOKEN_URL"], data=body), timeout=20) as r:
        print(json.load(r)["access_token"])
except urllib.error.HTTPError as e:
    sys.exit("Keycloak refused the registry-connector client-credentials grant: HTTP %s" % e.code)
except Exception as e:
    sys.exit("Could not obtain a registry-connector token from the token endpoint: %s" % type(e).__name__)
')
unset client_secret
[[ -n "$ADMIN_TOKEN" ]] || { echo "Keycloak returned no access token for registry-connector." >&2; exit 1; }
# Run a python program (argument 1, stdlib only) in the API pod. stdin carries the token on line 1,
# then the program; the program sees it as TOKEN.
pod_py() {
  { printf '%s\n' "$ADMIN_TOKEN"; printf '%s\n' "$1"; } |
    kubectl exec -i -n "$NAMESPACE" "${API_POD#pod/}" -- python -c 'import sys; TOKEN = sys.stdin.readline().strip(); exec(sys.stdin.read())'
}
# The upgrade exists to make this true: a request without a token must be refused.
pod_py '
import urllib.error, urllib.request
try:
    urllib.request.urlopen("http://127.0.0.1:8050/connectors/meta", timeout=10)
except urllib.error.HTTPError as e:
    if e.code not in (401, 403):
        raise SystemExit("Unauthenticated GET /connectors/meta answered HTTP %s, expected 401 or 403" % e.code)
    print("Unauthenticated GET /connectors/meta refused with HTTP %s" % e.code)
else:
    raise SystemExit("Unauthenticated GET /connectors/meta succeeded: the connector API is NOT admin-only")
'
pod_py '
import json, urllib.request
req = urllib.request.Request("http://127.0.0.1:8050/connectors/meta", headers={"Authorization": "Bearer " + TOKEN})
meta = json.load(urllib.request.urlopen(req, timeout=10))
print("Authenticated GET /connectors/meta answered; keys:", sorted(meta))
'
helm history "$RELEASE" -n "$NAMESPACE" --max 3
echo "Upgraded $RELEASE in $NAMESPACE to git (archive: $BACKUP_HOST:$BACKUP_DIR/$STAMP-connector-*)"
