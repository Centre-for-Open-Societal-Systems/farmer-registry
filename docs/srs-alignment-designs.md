# SRS alignment: proposed designs

Status: **proposal for review**. Nothing here is built yet.

This document covers four gaps found in a review of the farmer registry against the
*Farmer Registry Module SRS*. Each gap needs a design decision before it can be built:

| # | Gap | SRS |
|---|---|---|
| 3 | [Status model](#3-status-model) | FR-03, FR-08 |
| 4 | [Conflicts and merge](#4-conflicts-and-merge) | FR-12, FR-13, FR-14 |
| 6 | [Roles and geographic scope](#6-roles-and-geographic-scope) | FR-19 |
| 9 | [Audit](#9-audit) | FR-20 |

The same review produced three other pieces of work, handled in their own PRs: the dedup-route auth fix, phone
normalisation, and the SRS list view. Some SRS areas are out of scope for Gen2:

- Fayda verification: the DPI team owns it.
- ATI and commercial-registry ingestion.
- Local-language UI and performance.

The constraints are to stay on the pinned platform (`RP_VERSION=0.0.0-develop.384`, staff UI `1.2.1`), to prefer
extension code and metadata, and to use `docker/patches/patch_platform.py` only where a platform change can't be avoided.

Paths below are shortened:

| Short | Meaning |
|---|---|
| `EXT/` | `farmer-extension/src/openg2p_registry_farmer_extension/` |
| `core/` | the registry-platform core package |
| `iam_core/` | the iam-service library |

---

## 3. Status model

### Today
There are two unrelated fields.

| Field | Owner | Values | Who writes it |
|---|---|---|---|
| `record_status` | platform (`G2PRegister`) | ACTIVE, INACTIVE, ARCHIVED, plus `record_status_reason` | Change-request payloads only. Platform search, count and export default to ACTIVE. Also read by the reporting views and the dashboards. |
| `state` | farmer extension (`EXT/register_domain/models/farmer.py`) | DRAFT, PENDING, APPROVED, REJECTED, CANCELLED | `post_approve` and `post_ingest` force APPROVED, and a boot backfill sets NULL rows to APPROVED. |

A row only reaches the register after approval, so `state` is always APPROVED there. The other four values are
unreachable: DRAFT and PENDING belong to intake submissions and change requests.

`zz_farmer_header_layout.sql` binds the header status dropdown to `state`, but writes the reason to
`record_status_reason`. `post_approve` (`EXT/.../g2p_register_domain_service_farmer.py`) then resets `state` to APPROVED
on **every** approved farmer change request. So a status that staff pick in the header silently reverts, and the reason
they typed describes a change that never happened.

Gen1 parity: the 1.3 farmer registry has no `state`. Its header is bound to `record_status`.

### Proposal
Keep two axes, each with a single meaning:

1. **Visibility (platform):** `record_status` stays the coarse gate the platform already filters on.
2. **Lifecycle (extension):** a new column `lifecycle_status` holds the SRS states that exist once a record is in the
   register:

| SRS state | `lifecycle_status` | `record_status` | Set by |
|---|---|---|---|
| Draft, Pending Validation | — (still an intake submission or change request) | — | workflow |
| Verified | VERIFIED | ACTIVE | Fayda verification (DPI team). Reserved until then. |
| Active | ACTIVE | ACTIVE | ingest (default) |
| Inactive | INACTIVE | INACTIVE | staff, with a reason |
| Flagged Conflict | FLAGGED_CONFLICT | ACTIVE (stays visible) | dedup / conflict detection (see §4) |
| Suspended | SUSPENDED | INACTIVE | Federal Admin, with a reason |
| Merged | MERGED | ARCHIVED (drops out of every default search) | merge (see §4) |

Changes:
- `state` becomes a read-only projection and leaves the header. Rebind the header dropdown to `lifecycle_status`,
  keeping `statusReason` on `record_status_reason`. Stop the unconditional `state = "APPROVED"` in `post_approve`.
- Add a transition table in the extension, `ALLOWED = {from: {to, …}}`, following FR-03 (Any → Flagged Conflict,
  Flagged Conflict → Active/Verified, Active ↔ Inactive, Active → Suspended, Any → Merged, …). Enforce it in three
  places:
  - `validate_domain_attributes`: early rejection when a change request is created. This hook only sees the payload,
    so it loads the current row.
  - `pre_approve`: the authoritative check at approval time. Raising here aborts the approval. It also derives
    `record_status` from `lifecycle_status`.
  - `post_ingest`: new records start ACTIVE.
- Make a reason mandatory for transitions into INACTIVE, SUSPENDED or MERGED (FR-08).
- Transition authority (who may make which move) comes from §6 roles and AWE approver rules, not from code.

Migration: add the column and backfill it from `record_status` (ACTIVE → ACTIVE, INACTIVE → INACTIVE,
ARCHIVED → MERGED only where `merged_into_internal_record_id` is set, otherwise INACTIVE).
The list filter and header colours follow FR-08.

**Open questions:**
- Should VERIFIED wait for the DPI team's Fayda work?
- Is a *manual* "Verified" step wanted before then?

---

## 4. Conflicts and merge

### Today
- **Platform dedup** is advisory. The inline engine scores fuzzy first and last name plus exact birth date, with a
  threshold of 70, and writes result tables per intake and change request. Approval never checks them.
- **Farmer batch scan** (`POST /api/v1/farmer-registry/deduplicate`) groups exact matches on ID documents,
  foundational ID, phone (canonical `phone_e164` after the phone PR) and household overlap. It sets `is_duplicated`
  and writes `dedup_results_register_records`.
  - That table has a `status` column (default `FLAGGED`) that nothing uses.
  - The scan resets everything by default (`reset_existing=True`), which would wipe any human decision.
- **Change requests** store only the new payload. The previous values are the prior `g2p_register_history_*` snapshot.
- The platform has **no merge, link or "duplicate of" concept**.

### Proposal (all in the extension)
1. **Decisions survive rescans.** The batch scan upserts pairs instead of resetting them, and never re-flags a pair
   marked NOT_DUPLICATE. `dedup_results_register_records.status` takes the values FLAGGED, CONFIRMED_DUPLICATE,
   NOT_DUPLICATE and MERGED. New columns record who resolved a pair, when, and why.
2. **Flagging.** A farmer with an open (FLAGGED) pair gets `lifecycle_status = FLAGGED_CONFLICT` (§3). The existing
   `is_duplicated` is derived from the same rule.
3. **Resolution endpoints** (farmer router, permission-gated like the dedup routes):
   - list open pairs, with both records' current values side by side (FR-13);
   - mark a pair NOT_DUPLICATE or CONFIRMED_DUPLICATE, with a mandatory justification.
4. **Merge is an ordinary change request on the losing record.** This reuses approval, history and audit with no
   platform change:
   - the payload sets `lifecycle_status = MERGED`, `record_status = ARCHIVED`,
     `record_status_reason = 'Merged into <Farmer ID>'` and a new `merged_into_internal_record_id`;
   - `pre_approve` checks that the winner is ACTIVE and not itself merged;
   - `post_approve` repoints the loser's child rows (phones, lands, reg IDs, household links) to the winner and marks
     the pair MERGED;
   - the loser keeps its ID, and `merged_into_internal_record_id` is the redirect (FR-14).
5. **Field-level conflicts (FR-12).** Where one farmer's values disagree between sources, the history snapshots
   already give the old and new value per change request. A conflict view can diff two snapshots. A true
   per-field store with source priority (Fayda > ATI > Commercial) is only worth building once there is more than
   one external source, which Gen2 doesn't have.

Staff UI: the list gains the flag through the existing `is_duplicated` column and filter. The resolution screen is
the gap. It needs either an upstream platform page or a small page in the farmer dashboard app.

**Open questions:**
- Who can merge? The SRS says Federal Admin only.
- Should an open conflict block approval of further change requests on either record?

---

## 6. Roles and geographic scope

### Today
- The IAM catalog (`docker/local-dev/farmer-registry-iam-catalog.json`, `local/iam-register/payload.json`) defines 72
  `resource:action` permissions and 11 workflow roles, from Intake Officer to Technical Administrator. None of them is
  an SRS role.
- **Data policies:**
  - IAM stores row filters with REGISTER_RECORD, GEO or ATTRIBUTE targets; ALLOW or DISALLOW; and conditions on
    fields.
  - Each policy creates a Keycloak client role `DP_<mnemonic>`. A user gets the filter by holding that role.
  - Values are **static**: there is no substitution from the user's own claims.
- **AWE approvers** can be users, realm or client roles, Keycloak groups, expressions, or HTTP resolvers. Farmer seeds
  only named demo users.
- **Masking:** the platform has none. `national_id_masked` is just a stored column.

### Proposal
**Role mapping.** All permission names below already exist.

| SRS role | Permission set | Row scope |
|---|---|---|
| Federal Admin | Operations Administrator + Technical Administrator | none (national) |
| Regional Admin | changeRequest view/create/approve, intakeSubmission view/approve, register:view, registerHistory:view | `DP_region_<id>` |
| Woreda Officer | Data Editor + Intake Validator | `DP_woreda_<id>` |
| Field Officer | Intake Officer | `DP_woreda_<id>` |
| Data Entry Clerk | Intake Officer (no approve) | optional |
| Auditor | every `*:view` (register, registerHistory, changeRequest, intakeSubmission, verification, messages) | optional |
| Program Manager | register:view, registerScore:view, changeRequest:view | none |

Delivery:
1. **Catalog.** Add the seven roles to both local catalogs and to the Keycloak client roles (`keycloak-init.sh`),
   keeping the 11 existing roles until users move over.
   - The **cluster** IAM payload is read from the platform subchart, and a wrapper chart can't override it. Either
     change the platform chart, or give the farmer chart its own configmap plus a later hook Job that POSTs the full
     catalog.
   - IAM replaces each role's permission list with what the payload sends, so the payload must be complete.
2. **Geo scope.** Add a `region_level_value_id` projection next to `woreda_level_value_id`, since region names make
   fragile filter keys. Generate one data policy per region and per woreda from Master Data with a script that calls
   IAM `add_policy`. That gives about 14 regions plus the woredas actually in use. Assign `DP_…` roles to users with
   the role.
3. **Approvals.** AWE approver rules become `{"role": "Regional Admin", "client": "<release>-staff-portal"}`, replacing
   the named users. Routing to the approver *in the farmer's region* needs Keycloak groups per region, plus `region`
   in the AWE context fields (`g2p_registry_awe_policy_configurations.sql` sends none today).

**Pitfalls to design around:**
- **No DP role means no filter.** A scoped user who forgets their `DP_` role sees everything. Failing closed ("a
  scoped role with no DP role sees nothing") needs a `patch_platform.py` entry in the data-policy middleware.
- The three history version/date routes are not row-filtered.
- Only reads are filtered, and only on routes marked `@data_policy`.
- A misspelled `field_id` in a policy is silently ignored.

**Later or upstream:**
- Claim-based scoping, e.g. a `${claim.region_id}` placeholder. This would replace thousands of static policies with
  one.
- Field-level masking of Fayda ID for non-privileged roles (FR-19, §7.2).

**Open questions:**
- Do the SRS roles replace or sit alongside the workflow roles?
- Who assigns them? The SRS says Federal Admin only.

---

## 9. Audit

### Today
- The staff API's `AuditMiddleware` sends one CloudEvent per call to the external Audit Manager
  (`POST {url}/v1/auditmanager/events`, enabled in helm).
- **Captured:** actor (sub, name, username, roles, IP, session), action (the handler name), outcome, API path,
  status, and request id.
- **Not captured:** affected record ids, user agent, request body.
- Successful anonymous calls are skipped.
- **Delivery** is fire-and-forget: `create_task` with no reference kept, a 2 s timeout, and failures only logged.
  Events can be lost.
- **Data-change history** is separate and durable: `g2p_register_history_*` stores a full snapshot per approval with
  approver, change request and source.
- There is no UI for Audit Manager events, and its source (1.0.1) is not in this workspace.

### Proposal
1. **Richer events.**
   - Add `user_agent` to the event context (one line).
   - Add the affected ids (`internal_record_id`, `change_request_id`, `submission_id`, `register_id`). The handler has
     already consumed the request body, so the middleware must read and cache it before `call_next`, or controllers
     must set `request.state.audit_subject` (the partner API already does the equivalent with `audit_actor`).
   - Ship it as a `patch_platform.py` entry. Check first that body caching is safe with the pinned Starlette.
2. **No silent loss.** Write each event to an outbox table in the same process, and have a celery beat task deliver
   and retry with backoff, deleting on 202. The farmer build already produces the celery image. A cheaper interim
   step is keeping task references and retrying in-process, but that still loses events on a pod restart.
3. **Auditor access.** An Auditor role with view permissions only (§6) can already use version history
   (`registerHistory:view`), change-request and intake views. That meets FR-20's "authorised users can review" for data
   changes with no code.
   - Searching and exporting *access* events (logins, failed attempts, sensitive views) belongs to Audit Manager.
   - Raise with the platform team: whether it has a query API or UI, its immutability guarantees, and 7-year retention.
4. **Login and logout events** come from Keycloak event listeners. Enable them in the realm (the local realm has
   none).

**Open questions:**
- Is Audit Manager the system of record for FR-20, or do we need an in-registry audit table?

---

## Upstream backlog (staff UI / platform)

These list-view and export items (SRS FR-UI-02/03, FR-06, FR-16) can't be done reliably by patching the compiled
bundle. They should be contributed to the platform:

| Item | Where |
|---|---|
| Page-size selector (10/25/50/100) | `PaginationBar` / `usePageSize` |
| Filters persisted across reloads | `useFilters` (URL or sessionStorage) |
| Row ⋮ actions: view, edit, update status, history | `EntityListPage` / `DataTable` `rowActions` |
| "Select all N matching" across pages | `useRegisterRecordSelection` |
| Geo / dependent (Region → Woreda) filter type with API-sourced options | filter framework + `FilterBuilder` |
| Bulk status update / bulk change request API | core + staff API |
| **Register export** | Staff UI 1.2.1 ships the Export menu (XLSX / ZIP-CSV, selected or filtered), but the pinned backend (`develop.384`, core 1.1.1) has no export endpoint, queue or worker. It needs the platform upgrade that brings G2P-5584, plus `register:export` in the IAM catalog. Selection checkboxes in the table only appear alongside export. |
