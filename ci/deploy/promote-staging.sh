#!/usr/bin/env bash
# Deliver the chart develop built from this source tree to staging. Run by ci/pipelines/staging.groovy in a full checkout
# of the staging branch. Nothing is built: deliver_staging.sh of oan-helm adds the rc tag to the images New Dev ran,
# deploys them and publishes the rc chart. It fails if develop never built this tree and rolls Helm back on failure.
#
# Values are the oan-helm staging overlay, then the staging layers of this repository in the order the OAN chart uses.
# --reset-values drops the values saved in the release, so these files alone describe staging.
set -euo pipefail
set +x
: "${KUBECONFIG:?Jenkins must bind the staging kubeconfig}"
: "${IMAGE_TAG:?Validation image required}"
export DELIVERY_ENVIRONMENT=staging HELM_NAMESPACE=farmer HELM_RELEASE=farmer-registry

docker build -q -t "oan-ci/validation:$IMAGE_TAG" ci/validation > /dev/null
rm -rf .oan-helm
git clone --quiet --depth 1 --filter=blob:none --sparse \
  https://github.com/Centre-for-Open-Societal-Systems/oan-helm.git .oan-helm
git -C .oan-helm sparse-checkout set scripts/ci environments/staging/values

OAN_PROMOTED_VALUES=.oan-helm/environments/staging/values/farmer.yaml
flags=()
for layer in location outgestion registrant-auth dci-signing identity; do
  file=helm/environments/staging/farmer-$layer.yaml
  OAN_PROMOTED_VALUES=$OAN_PROMOTED_VALUES:$file
  flags+=(-f "$file")
done
export OAN_PROMOTED_VALUES

bash .oan-helm/scripts/ci/deliver_staging.sh openg2p-farmer-registry "$HELM_RELEASE" "$HELM_NAMESPACE" farmer.yaml \
  "${flags[@]}" --post-renderer ci/deploy/promote-renderer.sh

# The seed applies metadata with ON_ERROR_STOP=0; fail the delivery if OAN's checks do not hold.
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"' EXIT
CHECKS=farmer-extension/src/openg2p_registry_farmer_extension/meta_data/zz-oan/90_checks.sql
python3 scripts/operations/commons/check_seed_metadata.py "$CHECKS" > "$STATE/check_seed_metadata.py"
kubectl exec -i -n "$HELM_NAMESPACE" deploy/farmer-registry-staff-portal-api -c staff-portal-api -- \
  python3 - < "$STATE/check_seed_metadata.py"
