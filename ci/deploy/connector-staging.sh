#!/usr/bin/env bash
# Bring the staging Farmer connector (releases farmer-connector-credentials and farmer-registry-connector, namespace
# farmer) to oan-helm main's staging values on every promotion, the way crop and livestock upgrade their connector
# after the registry. Run by ci/pipelines/staging.groovy right after promote-staging.sh; it takes no parameters.
#
# What runs is oan-helm's own scripts/ci/deliver_staging_farmer_connector.sh with its chart (addons/farmer-connector,
# addons/farmer-connector-credentials) and its values (environments/staging/values/farmer-connector*.yaml):
# helm upgrade --install --reset-values --atomic --wait, so git is the only source of the values and a failed
# upgrade restores the previous revision (chart and values only). The images are the ones those values pin; nothing
# is built or tagged here. Without this step the release kept the values of its last operator deploy: after the
# qa move the registry and Keycloak were on qa.oanstaging.com while the connector still validated the old issuer
# (staging #45, connector-definitions: "Invalid issuer").
#
# Env: KUBECONFIG (set by the pipeline).
set -euo pipefail
: "${KUBECONFIG:?The pipeline must bind the staging kubeconfig}"
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

checkout=.oan-helm-connector
rm -rf "$checkout"
trap 'rm -rf "$checkout"' EXIT
git clone --quiet --depth 1 --filter=blob:none --sparse \
  https://github.com/Centre-for-Open-Societal-Systems/oan-helm.git "$checkout"
git -C "$checkout" sparse-checkout set scripts/ci environments/staging/values addons/farmer-connector \
  addons/farmer-connector-credentials
echo "oan-helm main $(git -C "$checkout" rev-parse --short=12 HEAD)"
helm history farmer-registry-connector -n farmer --max 2 || true
bash "$checkout/scripts/ci/deliver_staging_farmer_connector.sh"
helm history farmer-registry-connector -n farmer --max 2
