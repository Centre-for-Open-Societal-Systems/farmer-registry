#!/usr/bin/env bash
# Deploy the ODK connector for the farmer registry.
#
# The connector polls ODK Central and posts each submission to the registry's
# Partner API. It is its own helm release, not part of the registry chart, and
# not part of the per-build pipeline: it changes on its own cadence, and its
# chart's hooks create a database. crop and live run the same chart the same way.
#
#   ENVIRONMENT=far     ./ci/connector/deploy.sh <image tag>
#   ENVIRONMENT=staging ./ci/connector/deploy.sh <image tag>
#   DRY_RUN=1 ENVIRONMENT=far ./ci/connector/deploy.sh <tag>   render only
#
# Env:
#   KUBECONFIG      the cluster to deploy to (required)
#   ENVIRONMENT     which values file to use (required, no default)
#   NAMESPACE       default far
#   RELEASE         default farmer-connector
#   VALUES          overrides ci/connector/values-<environment>.yaml
#
# ENVIRONMENT is required and deliberately has no default. It used to select the
# values file by NAMESPACE, which is unsafe here: dev and staging are different
# clusters that both run the registry in a namespace called `far`, so a staging
# deploy silently picked up dev's values -- dev's connector hostname, dev's ODK
# Central URL, dev's database and pull-secret names. It would have come up
# looking healthy while polling the wrong ODK server.
#
# The release keeps its own values; only the image tags change, so an ODK
# password or pipeline edited in the UI survives a redeploy.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

TAG="${1:-${TAG:-}}"
NAMESPACE="${NAMESPACE:-far}"
RELEASE="${RELEASE:-farmer-connector}"
CHART="${CHART:-openg2p-connector-service/deploy/charts/openg2p-connector}"
ENVIRONMENT="${ENVIRONMENT:-}"
VALUES="${VALUES:-${ENVIRONMENT:+ci/connector/values-${ENVIRONMENT}.yaml}}"
DRY_RUN="${DRY_RUN:-}"

die() { echo "ERROR: $*" >&2; exit 1; }
note() { echo "=== $* ==="; }

[ -n "$TAG" ] || { echo "usage: $0 <image tag>" >&2; exit 2; }
[ -n "${KUBECONFIG:-}" ] || die "set KUBECONFIG to the target cluster"
[ -n "$VALUES" ] || die "set ENVIRONMENT (far | staging), or VALUES to a values file.
  There is no default: dev and staging both deploy into a namespace called 'far'
  on different clusters, so guessing from the namespace picks the wrong one."
[ -f "$CHART/Chart.yaml" ] || die "no chart at $CHART"
[ -f "$VALUES" ] || die "no values file at $VALUES"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

note "Target"
echo "server:   $(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
echo "release:  $RELEASE in $NAMESPACE"
# Printed next to the server on purpose: both clusters use the namespace 'far',
# so the values file is the only thing that says which environment this is.
echo "values:   $VALUES"
echo "chart:    $CHART ($(grep -m1 '^version:' "$CHART/Chart.yaml" | awk '{print $2}'))"
echo "images:   */connector-{service,ui}:$TAG"

# The postgres-init subchart is vendored under charts/, so this resolves
# offline; it still runs, to fail early if the lock and the tree disagree.
helm dependency build "$CHART" >/dev/null 2>&1 || true

# Keep whatever the release already has — ODK credentials, pipelines pointed at
# a particular project — and change only the image tags.
LIVE=""
if helm get values "$RELEASE" -n "$NAMESPACE" -o yaml > "$WORK/live.yaml" 2> "$WORK/err"; then
    echo "reusing the release's own values ($(wc -l < "$WORK/live.yaml") lines)"
    LIVE="-f $WORK/live.yaml"
else
    grep -q 'release: not found' "$WORK/err" || { cat "$WORK/err" >&2; die "could not read the release's values"; }
    echo "no $RELEASE release yet: first install"
fi

# shellcheck disable=SC2086  # LIVE is an optional -f pair
set -- $LIVE -f "$VALUES" \
    --set "api.image.tag=$TAG" \
    --set "worker.image.tag=$TAG" \
    --set "beat.image.tag=$TAG" \
    --set "ui.image.tag=$TAG"

note "Render"
helm template "$RELEASE" "$CHART" -n "$NAMESPACE" "$@" > "$WORK/rendered.yaml"
echo "rendered $(grep -c '^kind:' "$WORK/rendered.yaml" || true) objects:"
{ grep -oE 'image: *"?[^" ]+' "$WORK/rendered.yaml" || true; } | sed -E 's/image: *"?//' | sort -u | sed 's/^/  /'
if [ -n "$DRY_RUN" ]; then
    note "DRY_RUN: nothing applied"
    exit 0
fi

note "helm upgrade"
helm upgrade --install "$RELEASE" "$CHART" -n "$NAMESPACE" "$@" --timeout 10m

# The UI image proxies to a fixed upstream named connector-api, while the chart
# names its service after the release. nginx resolves upstreams at startup, so
# without this alias the UI pod dies with
#   [emerg] host not found in upstream "connector-api"
# and the rollout times out. The file has been in git without anything applying
# it, so both dev and staging hit this and were fixed by hand. The namespace is
# taken from $NAMESPACE rather than the file, which pins its own.
ALIAS="$(dirname "${BASH_SOURCE[0]}")/connector-api-alias.yaml"
if [ -f "$ALIAS" ]; then
    note "connector-api alias"
    kubectl apply -n "$NAMESPACE" -f "$ALIAS"
else
    echo "WARNING: $ALIAS is missing; the UI will crash-loop on a fresh install" >&2
fi

note "Rollout"
for d in api worker beat ui; do
    kubectl get deploy "$RELEASE-$d" -n "$NAMESPACE" >/dev/null 2>&1 || continue
    kubectl rollout status "deploy/$RELEASE-$d" -n "$NAMESPACE" --timeout=300s
done

note "Health"
kubectl run "connector-check-$$" --rm -i --restart=Never -n "$NAMESPACE" \
    --image=curlimages/curl:8.11.1 --command -- \
    curl -sS -o /dev/null -w 'connector api /health: HTTP %{http_code}\n' \
    --max-time 10 "http://$RELEASE-api/health" || true

cat <<EOF

Next, if this is a fresh environment:
  1. Publish the XLSForm in ODK Central and attach its media CSVs (odk/README.md).
  2. Register the partner the connector posts as:
       insert into g2p_partners (partner_id, partner_mnemonic, keymanager_reference_id, is_active)
       values ('farmer-partner', 'farmer-partner', 'farmer-key-ref', true)
       on conflict (partner_id) do nothing;     -- in the master_data database
  3. Point the pipeline at the form, in the connector UI at
     https://connector-farmer-registry.far.openg2p.test, or by setting
     CONNECTOR_ODK_* on the release so it seeds itself.
EOF
