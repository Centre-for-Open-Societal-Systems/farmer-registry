> Historical server diagnosis and rollout prerequisites from PR #91. The repository now uses the upstream RC layout; old Jenkins/local-gen2 commands below are not the new deployment procedure. See [current adoption notes](coss-upstream-adoption.md).

> Subsequent 2026-10-15 work completed the dev coordinate/document-history repairs
> and the approved shared COSS geography migration. Those schema prerequisites
> below are historical, not current blockers. PM onboarding/issuer and ODK
> publication/end-to-end acceptance were not completed by that operation. See
> [the current migration evidence and remaining work](odk-geography-rollout.md).

# New dev: ODK connector rejection and single-PR rollout

Inspected over read-only SSH on 2026-10-15 IST (2026-10-14 UTC).
Pipeline: `ad8ac90635574462ac461741f336a0c7`, at
<https://connector.farmer-dev.oanstaging.com/pipelines/ad8ac90635574462ac461741f336a0c7?tab=runs>.
No server configuration, data, deployments or run state were changed.

## Confirmed failure

The connector API, worker and beat are running. ODK login, submission/repeat
fetches and both attachment downloads succeed. The pipeline already uses
`FARMER_ODK_MODEL`, sender `farmer-partner`, and register `Farmer`.

The registry responds HTTP 200 with the application error
`[REGP-ERR-001] PARTNER_NOT_REGISTERED`. At 21:36 UTC there were 21 failed
runs and no successful runs for this pipeline; subsequent scheduled polls
continued to fail on the same source event. The connector correctly treats
the response body as a rejection and records dead-letter entries.

Two independent Partner Management prerequisites are missing:

1. **Issuer mismatch.** The registry's client-credentials request succeeds.
   Its token issuer is
   `https://keycloak.commons-dev.oanstaging.com/realms/staff`, but PM's
   effective `auth_default_issuers` is
   `["http://commons-keycloak:80/realms/staff"]`. An authenticated
   `GET /partners/farmer-partner` returns HTTP 401, `Unauthorized. Unknown Issuer`.
   The running PM settings give explicitly supplied `PARTNER_MANAGER_AUTH_*`
   values precedence over `COMMON_AUTH_*`. The latter already contains the
   correct public issuer; changing only that prefix cannot fix this instance.
2. **Missing partner.** Read-only queries of shared PM found neither
   `farmer-partner` nor its normalized fallback `PARTNER_FARMER_PARTNER` in
   `pm_partners`, and no keys for `farmer-partner`. The public `/keys/` lookup
   returns HTTP 404 for both IDs. An old Master Data partner row does not
   register a sender with PM.

The token already carries client role `partner_manager` under
`commons-services-staff-portal`, matching PM's effective admin client and role.
No role grant is needed for the observed service account. Both the existing
short PM service name and the namespace-qualified name resolve to the same
service; DNS is not the cause of this rejection.

The rc.544 schema gate also fails: 24 register/history coordinate columns are
still `character varying`, and `g2p_register_document_history.event_type` is
absent. These are later intake/promotion blockers, separate from the current
partner rejection.

## Read-only recheck: 2026-10-15 03:35-03:36 UTC

The scheduled worker still fetches one ODK submission and downloads both
attachments with HTTP 200. Registry returns HTTP 200 with
`[REGP-ERR-001] PARTNER_NOT_REGISTERED`; each observed poll reports
`fetched: 1, success: 0, failed: 1`. Partner API logs confirm the same rejection.

Read-only database transactions found neither partner ID above in `pm_partners`
and zero `incoming_raw_data` messages with the connector's `farmer_profile:`
prefix. PM's running environment still has the conflicting internal/public
issuer values described above. This recheck did not request a fresh token or
repeat the authenticated PM probe.

`FARMER_ODK_MODEL` maps to Farmer intake form
`a1a4d25a-1cd4-4356-abac-8782382649`. Its AWE policy is configured as
`registry.intake_form.farmer` (type `registry.intake_form`). Approval is attached,
but no ODK message has reached ingestion to initiate it. The local pinned RC
worker calls intake finalization after saving sections; that code inspection
is not evidence of a successful server ODK approval.

The schema prerequisites are also unchanged: 24 register/history coordinate
columns remain `character varying`, and document history lacks `event_type`.
All commands were read-only; no configuration changes, onboarding, submissions,
replays or migrations were performed.

## Operator repair sequence

The implementation and verified DNS map are in the
[PM issuer and approval rollout](pm-issuer-and-approval-rollout.md). It includes
the newly confirmed PM/IAM ingress collision and PM browser logout correction,
the pinned Helm overlay, manifest guard, and local PM approval evidence.

These are pending server operations, not actions performed during diagnosis.
Keep the existing Commons Base 2.3.3 / Services 2.3.4-rc.245 releases.

1. In the platform-owned Commons values, correct PM staff API's effective
   issuer settings and keep the two prefixes consistent. For this dev server:

   ```yaml
   PARTNER_MANAGER_AUTH_DEFAULT_ISSUERS: '["https://keycloak.commons-dev.oanstaging.com/realms/staff"]'
   COMMON_AUTH_DEFAULT_ISSUERS: '["https://keycloak.commons-dev.oanstaging.com/realms/staff"]'
   PARTNER_MANAGER_AUTH_DEFAULT_JWKS_URLS: '["http://commons-keycloak:80/realms/staff/protocol/openid-connect/certs"]'
   COMMON_AUTH_DEFAULT_JWKS_URLS: '["http://commons-keycloak:80/realms/staff/protocol/openid-connect/certs"]'
   ```

   These are environment entries, not a complete Helm values file. Persist
   them under the deployed PM staff API's env-values mapping and roll out that
   service through its owning deployment process. Preserve any other approved
   issuers and their corresponding JWKS entries. Retain auth, signature and
   role checks. Verify a fresh registry service token reaches PM without 401/403.
2. Through the PM staff UI/API, onboard and approve partner ID
   `farmer-partner`, using the intended connector public key, until its status
   is `active`. Do not insert a database row directly or rerun all seed jobs.
   Verify `GET /partners/farmer-partner` returns 200 and `status: active` using
   the registry's service account. The local demo key is not a server key.
3. Complete the backed-up coordinate migration described in
   [the platform upgrade guide](registry-platform-1.2.2-upgrade.md) and the
   explicit [document-history migration](../ci/gen2/migrations/document_history_event_type.sql)
   before processing intake records with rc.544. Quiesce registry writers for
   the migration and restart their DB connections afterward. Run the read-only
   gate again; PR #91 deliberately blocks deployment while the schema is old.
4. Deploy PR #91 after the documented prerequisites and existing seed-data
   repairs are satisfied. Its registry changes include numeric coordinate
   normalization and the pinned RC worker, validated with local intake approval.
5. Check whether the scheduled poll has already delivered the source event
   before replaying it. If it has not, replay one corresponding DLQ entry;
   avoid bulk replay of repeated entries for the same event. Verify one registry
   message, completed ingestion, retained attachments/geography, AWE approval,
   and register promotion. A connector success only proves registry acceptance,
   not completion of asynchronous processing.

The legacy `/partner/ingest_data` route does not cryptographically verify its
envelope signature. Partner onboarding fixes sender eligibility; it does not
add signature verification. See [current acceptance limits](../local/upstream/README.md#evidence-and-remaining-work).

## One Farmer PR

[PR #91](https://github.com/Centre-for-Open-Societal-Systems/farmer-registry/pull/91)
is the sole Farmer PR for this Gen2 intake/ODK rollout and includes DevOps PR #92.

- **#88 is superseded for this rollout:** #91 already contains the coordinate
  migration script inherited from develop, its operating instructions, and a
  read-only deployment gate. Schema migration is an explicit backed-up operator
  step. The automatic pre-upgrade hook proposed by #88 is not a prerequisite
  and is intentionally not enabled.
- **#89 is superseded for this rollout:** it upgrades the old `far` Commons
  topology to Services 2.3.3. New dev already uses the correct shared releases
  in `commons`; do not run that legacy upgrade. The applicable PM issuer and
  onboarding requirements are captured above, with the current server's
  actual issuer. The working local equivalent is included in #91.
- Unrelated bulk-upload/dashboard-auth PRs are outside this rollout.

One PR does not eliminate the pending platform configuration and data steps.
Merging #91 alone cannot repair shared PM or migrate the existing server data.
