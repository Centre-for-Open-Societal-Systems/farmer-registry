#!/usr/bin/env bash
# Read-only check. The platform owner provisions these credentials in farmer;
# farmer-ci does NOT get permission to read commons Secrets or upgrade commons.
# Query namespace-local Secret objects but emit ONLY key-presence, never values.
set -euo pipefail
NS="${HELM_NAMESPACE:-farmer}"
RELEASE="${HELM_RELEASE:-farmer-registry}"

check_key() {
  local secret="$1" key="$2"
  local present
  present=$(kubectl get secret "$secret" -n "$NS" \
    -o "go-template={{if index .data \"$key\"}}present{{end}}")
  if [ "$present" != present ]; then
    echo "Missing required Secret key: $NS/$secret ($key). Ask the platform owner to provision it." >&2
    exit 1
  fi
  echo "Secret reference OK: $NS/$secret ($key)"
}

check_key commons-postgresql postgres-password
check_key commons-keycloak admin-password
for key in root-user root-password readonly-user readonly-password; do
  check_key commons-minio "$key"
done
check_key master-data-db-user master-data-db-user-password
check_key awe-db-user awe-db-user-password
# Upstream marks this optional at the Kubernetes level, but registry APIs/workers
# need it for service-token calls to Master Data/partner-management.
check_key commons-services-staff-portal client_secret

# rc.544's db-seed health wait needs this existing platform-owned alias. Its
# ownership is deliberately irrelevant: this chart never creates/adopts it.
alias_target=$(kubectl get service commons-services-awe -n "$NS" --ignore-not-found \
  -o 'go-template={{.spec.type}}|{{.spec.externalName}}')
if [ "$alias_target" != "ExternalName|commons-services-awe.commons.svc.cluster.local" ]; then
  echo "Missing or incorrect commons-services-awe alias in $NS; expected an ExternalName to commons." >&2
  echo "Ask the platform owner to provision/correct it; no resources were changed." >&2
  exit 1
fi

# Stop an existing rc.384-era database from being served by rc.544 before its
# required varchar-to-Float migration. This does NOT run the migration or seed.
deployment=$(kubectl get deployment "$RELEASE-staff-portal-api" -n "$NS" --ignore-not-found -o name)
if [ -n "$deployment" ]; then
  HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  kubectl exec -i -n "$NS" "deploy/$RELEASE-staff-portal-api" -c staff-portal-api -- \
    python3 - < "$HERE/check_geo_schema.py"
else
  echo "No existing staff API pod: first-install schema/restored-DB readiness must be confirmed by the platform owner."
fi
echo "Gen2 namespace-local prerequisites OK (shared RC version must be checked by the platform owner)."
