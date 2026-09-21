-- Values first, so the insert and the update below share one list.
WITH v("id","policy_key","version","name","description","status","artifact_type",
       "created_by","forbid_self_approval","forbid_repeat_approvers") AS (VALUES
    ('576a69ba-a2ca-4c34-80b7-952e8c5a86f8', 'registry.change_request.farmer', 1, 'Policy for Farmer Change Request', NULL::text, 'active', 'registry.change_request', 'seed', FALSE, FALSE),
    ('57f40743-266c-4e25-9a16-fd45483f904c', 'registry.change_request.household', 1, 'Policy for Household Change Request', NULL::text, 'active', 'registry.change_request', 'seed', FALSE, FALSE),
    ('e725a02c-6120-4e33-b4ec-294a38b07b18', 'registry.intake_form.farmer', 1, 'Policy for Farmer Intake Form', NULL::text, 'active', 'registry.intake_form', 'seed', FALSE, FALSE),
    ('fb51a862-d2ed-460d-8e1f-929cbeabdd01', 'registry.intake_form.household', 1, 'Policy for Household Intake Form', NULL::text, 'active', 'registry.intake_form', 'seed', FALSE, FALSE)
),
inserted AS (
    INSERT INTO "public"."approval_policy" (
        "id",
        "policy_key",
        "version",
        "name",
        "description",
        "status",
        "artifact_type",
        "created_by",
        "forbid_self_approval",
        "forbid_repeat_approvers",
        "created_at",
        "updated_at"
    )
    SELECT v."id", v."policy_key", v."version", v."name", v."description", v."status",
           v."artifact_type", v."created_by", v."forbid_self_approval",
           v."forbid_repeat_approvers", NOW(), NOW()
    FROM v
    -- Untargeted DO NOTHING, not ON CONFLICT ("id"): `approval_policy` also carries
    -- uq_policy_key_version, and the platform seeds `registry.change_request.household`
    -- under a DIFFERENT id. Targeting "id" left that natural-key clash unguarded, so
    -- the whole multi-row statement aborted and NONE of the policies landed — farmer
    -- included. Untargeted catches every unique constraint and skips only the
    -- offending row.
    ON CONFLICT DO NOTHING
)
-- Existing rows: refresh the fields this seed owns, so an edit here (a rename, a
-- forbid_* flip) reaches environments seeded before it. This is a separate UPDATE
-- rather than ON CONFLICT DO UPDATE because of the constraint clash above; it is
-- matched on OUR ids, so the platform's household policy is never touched, and
-- rows the INSERT just created are invisible to it (same snapshot). status and
-- version are lifecycle fields AWE owns after creation and are left alone. The
-- predicate keeps a re-run a no-op with updated_at untouched.
UPDATE "public"."approval_policy" p
SET "name"                    = v."name",
    "description"             = v."description",
    "forbid_self_approval"    = v."forbid_self_approval",
    "forbid_repeat_approvers" = v."forbid_repeat_approvers",
    "updated_at"              = NOW()
FROM v
WHERE p."id" = v."id"
  AND (p."name"                    IS DISTINCT FROM v."name"
    OR p."description"             IS DISTINCT FROM v."description"
    OR p."forbid_self_approval"    IS DISTINCT FROM v."forbid_self_approval"
    OR p."forbid_repeat_approvers" IS DISTINCT FROM v."forbid_repeat_approvers");
