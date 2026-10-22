# Dedicated registry staff accounts

The new-dev accounts are `<registry>.intake`, `<registry>.l1`, and
`<registry>.l2` (registry: farmer, livestock, cropsown). Intake can create/submit;
L1 approves the existing first stage; Farmer L2 approves its second stage.
Livestock/Crop Sown L2 are read-only because their existing workflows have one
stage. Each L2 alone receives its own dashboard's `Dashboard Viewer` role.

## Seed contract

`docker/db-seed/staff_access.py` is shared byte-for-byte across the three repos.
The ordinary db-seed entrypoint invokes it after metadata; it is disabled unless
`STAFF_SEED_ENABLED=true`. A separate optional `staffAccess` Helm hook runs the
same script with the db-seed image after normal metadata/client registration.
Default chart renders and staging remain unchanged. Build/publish the changed
db-seed image before enabling the hook; existing images do not contain the script.

Set `staffAccess.enabled=true`, `existingSecret`, `imagePullSecrets`, the actual
`clientId`/`dashboardClientId` where these differ, `twoStages`, and `policyKeys`
to the environment's existing intake policies. Never assume dev's policy keys,
namespaces, credentials or stage layout apply to staging. The canonical chart
source is oan-helm; the matching registry chart source retains the same hook.

Create the referenced Secret in the release namespace with these environment
keys (no literal credentials belong in values or Git):

- `STAFF_SEED_KEYCLOAK_URL`, `STAFF_SEED_REALM` (normally staff),
  `STAFF_SEED_ADMIN_USER`, `STAFF_SEED_ADMIN_PASSWORD`.
- `STAFF_SEED_PASSWORD_INTAKE`, `STAFF_SEED_PASSWORD_L1`, `STAFF_SEED_PASSWORD_L2`:
  distinct, at least 16 characters. Used only when creating an account.
- `IAM_PGHOST`, `IAM_PGPORT`, `IAM_PGDATABASE`, `IAM_PGUSER`, `IAM_PGPASSWORD`.
- `AWE_PGHOST`, `AWE_PGPORT`, `AWE_PGDATABASE`, `AWE_PGUSER`, `AWE_PGPASSWORD`.

The optional `STAFF_SEED_EMAIL_DOMAIN` defaults to `example.invalid` for these
technical dev profiles. These addresses do not represent staff contact details.
No notification is sent and passwords are permanent. Populate real profile
addresses explicitly when repurposing accounts for people.

Provisioning requires existing application permissions, Keycloak clients and
dashboard role. It fails on missing policies, unexpected stage topology or
unexpected existing user client grants. SQL commits per database under an
advisory lock; Keycloak/SQL are not one transaction. Retry after a failure rather
than deleting users. Existing passwords, populated profiles, unrelated users,
approval stage modes/counts and pending task assignees are preserved.

Only explicitly listed intake-policy rules are reassigned: Farmer L1/L2 replace
the old named stage approvers while existing admin fallbacks remain. Livestock's
active resolver rule becomes the all-location L1 named assignee; retired stages
remain retired. Crop's existing single-stage rules target L1, so `all` mode does
not introduce an extra required approver. Pending tasks retain their existing
assignees, including tasks already active in later stages.

Credentials are documented on the existing Confluence `Openg2p setup` page.
New-dev passwords are retained in `commons/registry-staff-access`; future hook
Secrets must use the approved credentials for their own environment. No staging
resources have been changed and no automatic password rotation is performed.
