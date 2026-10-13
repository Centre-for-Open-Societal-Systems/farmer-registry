#!/usr/bin/env bash
# Read-only check. The platform owner provisions these credentials in far;
# farmer-ci does NOT get permission to read common Secrets or upgrade commons.
# Query namespace-local Secret objects but emit ONLY key-presence, never values.
set -euo pipefail
NS="${HELM_NAMESPACE:-far}"
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

# Helm cannot take over a manually created alias. Fail BEFORE any upgrade rather
# than adopting/deleting a resource that might belong to somebody else's release.
alias_json=$(kubectl get service commons-services-awe -n "$NS" --ignore-not-found \
  -o 'go-template={{.spec.externalName}}|{{index .metadata.annotations "meta.helm.sh/release-name"}}|{{index .metadata.annotations "meta.helm.sh/release-namespace"}}|{{index .metadata.labels "app.kubernetes.io/managed-by"}}')
if [ -n "$alias_json" ] && [ "$alias_json" != "commons-services-awe.common.svc.cluster.local|$RELEASE|$NS|Helm" ]; then
  echo "commons-services-awe exists in $NS without the expected farmer release ownership/target." >&2
  echo "Have the platform owner resolve the legacy alias before upgrading; no resources were changed." >&2
  exit 1
fi
echo "Gen2 namespace-local prerequisites OK (shared RC version must be checked by the platform owner)."
