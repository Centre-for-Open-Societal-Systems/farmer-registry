#!/usr/bin/env bash
# Bring the staging Farmer dashboard UI (release farmer-registry-dashboard, namespace farmer) to oan-helm main's staging
# values on every promotion, as crop and livestock deliver theirs. Run by ci/pipelines/staging.groovy after the connector
# definitions; it takes no parameters.
#
# Chart repository/farmer-registry-dashboard-0.1.2.tgz with environments/staging/values/farmer-dashboard.yaml (the
# release scripts/ci/deliver_staging_dashboards.sh installs): the qa host on istio-system/staging. The chart generates
# its Keycloak client secret, registers the client and the staff-portal tile (IAM setup hook) and refreshes its own ECR
# pull secret, so nothing is set by hand. helm upgrade --install --reset-values --atomic: git is the only source of the
# values and a failed upgrade restores the previous revision. Without this step the release kept the 5 Nov hand
# install on the old host, and farmer-registry-dashboard.qa.oanstaging.com answered 404.
#
# Env: KUBECONFIG (set by the pipeline).
set -euo pipefail
: "${KUBECONFIG:?The pipeline must bind the staging kubeconfig}"
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

checkout=.oan-helm-dashboard
rm -rf "$checkout"
trap 'rm -rf "$checkout"' EXIT
git clone --quiet --depth 1 --filter=blob:none --sparse \
  https://github.com/Centre-for-Open-Societal-Systems/oan-helm.git "$checkout"
git -C "$checkout" sparse-checkout set --no-cone \
  /repository/farmer-registry-dashboard-0.1.2.tgz /environments/staging/values/farmer-dashboard.yaml
echo "oan-helm main $(git -C "$checkout" rev-parse --short=12 HEAD)"
helm upgrade --install farmer-registry-dashboard "$checkout/repository/farmer-registry-dashboard-0.1.2.tgz" \
  --namespace farmer --values "$checkout/environments/staging/values/farmer-dashboard.yaml" \
  --reset-values --atomic --wait --timeout 10m
helm history farmer-registry-dashboard -n farmer --max 2
