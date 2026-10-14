# Appended to the existing initializer so it reuses its kcadm helpers.
# This runs only through the explicit setup profile, never on ordinary up.
# The legacy helper suppresses errors; new assignments must fail visibly.
assign_client_role() {
  "${KCADM}" add-roles -r "${KEYCLOAK_REALM}" --uusername "$1" \
    --cclientid "$2" --rolename "$3" >/dev/null
}
ensure_client "commons-services-staff-portal" \
  -s enabled=true -s publicClient=false -s serviceAccountsEnabled=true \
  -s standardFlowEnabled=false \
  -s secret="${COMMONS_CLIENT_SECRET:-dev-commons-client-secret}"
ensure_client master-data -s enabled=true -s publicClient=true -s standardFlowEnabled=true \
  -s 'redirectUris=["http://masterdata.farmer.localtest.me:3110/*"]' -s 'webOrigins=["+"]'
ensure_client consent-manager -s enabled=true -s publicClient=true -s standardFlowEnabled=true \
  -s 'redirectUris=["http://cm.farmer.localtest.me:3060/*"]' -s 'webOrigins=["+"]'
ensure_client_role "commons-services-staff-portal" partner_manager
assign_client_role "service-account-commons-services-staff-portal" "commons-services-staff-portal" partner_manager
ensure_client_role master-data MASTER_DATA_ADMIN
assign_client_role service-account-commons-services-staff-portal master-data MASTER_DATA_ADMIN
for role in CONSENT_MANAGER_ADMIN CONSENT_MANAGER_APPROVER; do
  ensure_client_role consent-manager "$role"
  assign_client_role "${KEYCLOAK_STAFF_ADMIN_USER}" consent-manager "$role"
  assign_client_role service-account-commons-services-staff-portal consent-manager "$role"
done
for user in "${KEYCLOAK_DEV_USER}" "${KEYCLOAK_STAFF_ADMIN_USER}"; do
  assign_client_role "$user" "commons-services-staff-portal" partner_manager
  assign_client_role "$user" master-data MASTER_DATA_ADMIN
done
