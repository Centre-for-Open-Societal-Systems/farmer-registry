#!/bin/sh
# Upgrade the shared platform services (`commons-services` release) in the
# farmer namespace to the chart version pinned below, with the overlay and the
# Master Data schema top-up kept next to this script. See docs/commons-services-upgrade.md.
#
# Run once per environment, deliberately, by the standalone Jenkins job in this
# directory or by anyone holding that cluster's kubeconfig:
#
#   KUBECONFIG=... ci/commons-services/upgrade.sh
#
# Not part of the registry's per-build pipeline: the chart's post-upgrade hooks
# (geo seed, iam-register) re-run on every helm upgrade, and the shared services
# change on their own cadence, not on every farmer commit.
#
# Upgrade only. The release's live values carry the environment's hostnames and
# wiring and are kept; a missing release means the platform was never installed
# here, which is not this script's job.
set -eu

NAMESPACE="${NAMESPACE:-far}"
RELEASE="${RELEASE:-commons-services}"
# Master Data 1.1.0-rc.55 (serves the current /geo route names), IAM 1.4.0-rc.90,
# audit-manager 1.0.1. docs/commons-services-upgrade.md: "Why 2.3.0-rc.217".
CHART_VERSION="${CHART_VERSION:-2.3.0-rc.217}"
CHART="openg2p-gitlab/openg2p-commons-services"
# The registry release whose staff-ui pod the final check runs from.
REGISTRY_RELEASE="${REGISTRY_RELEASE:-farmer-registry}"

HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

: "${KUBECONFIG:?set KUBECONFIG to the kubeconfig of the target cluster}"

helm repo add openg2p-gitlab https://gitlab.com/api/v4/projects/84460547/packages/helm/stable >/dev/null 2>&1 || true
helm repo update openg2p-gitlab >/dev/null

# 1. Where we start from, and the handle for rolling back.
helm get values "$RELEASE" -n "$NAMESPACE" -o yaml > "$WORK/values-live.yaml"
REV=$(helm list -n "$NAMESPACE" -f "^$RELEASE\$" -o json | sed -n 's/.*"revision":"\([0-9]*\)".*/\1/p')
echo "=== $RELEASE in $NAMESPACE is at revision $REV; chart $(helm list -n "$NAMESPACE" -f "^$RELEASE\$" -o json | sed -n 's/.*"chart":"\([^"]*\)".*/\1/p') ==="
echo "=== rollback: helm rollback $RELEASE $REV -n $NAMESPACE ==="
cp "$WORK/values-live.yaml" "./$RELEASE-values-rev$REV.yaml"
echo "=== live values saved to ./$RELEASE-values-rev$REV.yaml ==="

# 2. Master Data schema top-up, inside the current API pod: it holds the DB
#    settings under either env prefix (GEN2_* on the old build, plain on the
#    new) and ships asyncpg. Idempotent, so re-running is safe.
echo "=== master-data schema top-up ==="
kubectl exec -i -n "$NAMESPACE" "deploy/$RELEASE-master-data-api" -- \
    python -c "$(cat "$HERE/apply-sql-in-pod.py")" < "$HERE/master-data-schema-topup.sql"

# 3. Render exactly what the upgrade applies, for the log.
helm template "$RELEASE" "$CHART" --version "$CHART_VERSION" -n "$NAMESPACE" \
    -f "$WORK/values-live.yaml" -f "$HERE/values-far.yaml" > "$WORK/rendered.yaml"
echo "=== rendered $(wc -l < "$WORK/rendered.yaml") lines; images: ==="
grep -E '^ *image:' "$WORK/rendered.yaml" | sed 's/^ *//' | sort -u

# 4. Upgrade. The hook Jobs delete their pod when they give up and the log goes
#    with it, so copy hook pod logs while helm runs and print them on failure.
LOGDIR="$WORK/hook-logs"; mkdir -p "$LOGDIR"
( while sleep 5; do
    for P in $(kubectl get pods -n "$NAMESPACE" -o name 2>/dev/null | grep -E "/$RELEASE-.*(seed|register|init)-"); do
        kubectl logs "$P" -n "$NAMESPACE" --all-containers --tail=100 > "$LOGDIR/${P#pod/}.log" 2>&1 || true
    done
  done ) &
WATCHER=$!
trap 'kill $WATCHER 2>/dev/null; wait $WATCHER 2>/dev/null; rm -rf "$WORK"' EXIT

echo "=== helm upgrade $RELEASE -> $CHART $CHART_VERSION ==="
if ! helm upgrade "$RELEASE" "$CHART" --version "$CHART_VERSION" -n "$NAMESPACE" \
        -f "$WORK/values-live.yaml" -f "$HERE/values-far.yaml" --timeout 20m; then
    for F in "$LOGDIR"/*.log; do
        [ -f "$F" ] || continue
        echo "=== $(basename "$F" .log): last 100 log lines ==="
        cat "$F"
    done
    echo "Upgrade failed. Roll back with: helm rollback $RELEASE $REV -n $NAMESPACE" >&2
    exit 1
fi

kubectl rollout status "deployment/$RELEASE-master-data-api" -n "$NAMESPACE" --timeout=300s

# 5. The reason this exists (G2R-172): the master-data the staff UI talks to
#    must serve the current geo route names.
echo "=== master-data geo routes as seen from the staff UI pod ==="
ROUTES=$(kubectl exec -n "$NAMESPACE" "deploy/$REGISTRY_RELEASE-staff-portal-ui" -- \
    sh -c 'wget -qO- "$MASTERDATA_BACKEND_API_URL/openapi.json"' | grep -oE '"/geo/[a-z_0-9]+"' | sort -u)
echo "$ROUTES"
echo "$ROUTES" | grep -q '"/geo/get_all_geo_levels"' || {
    echo "master-data does not serve /geo/get_all_geo_levels after the upgrade" >&2
    exit 1
}
# 6. The chart renders AWE's config with one accepted issuer, so this upgrade
#    overwrites any extra issuers added by hand -- a public portal's Keycloak,
#    typically. Without them AWE answers 401 on tokens from that Keycloak and the
#    portal shows AWE-ERR-006, as soon as an AWE pod restarts.
echo "=== AWE accepts these issuers now ==="
kubectl get cm "$RELEASE-awe-config" -n "$NAMESPACE" -o jsonpath='{.data.config\.yaml}' 2>/dev/null \
    | sed -n '/keycloak:/,/audience:/p' | sed 's/^/    /' || true
echo "=== if an environment reaches Keycloak by another hostname, re-add it before using the portal ==="

echo "=== done: $RELEASE now at revision $(helm list -n "$NAMESPACE" -f "^$RELEASE\$" -o json | sed -n 's/.*"revision":"\([0-9]*\)".*/\1/p') ==="
