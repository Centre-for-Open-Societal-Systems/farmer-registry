-- AWE callback registration for this registry. AWE signs its decision webhooks with secret_hash and
-- the staff portal API verifies them with the registry's Secret <release>-awe-callback-hmac.
--
-- The platform chart mints that Secret once (lookup-guarded, resource-policy keep) and mints it
-- again only if the Secret is gone (a namespace delete or reinstall). The platform template's upsert
-- updates caller_service only, so after such a re-mint AWE kept the old value and every decision
-- webhook was refused with 401 (Farmer on staging, Secret re-minted 31 Oct 2026). This upsert also
-- writes the current value, so each db-seed run brings AWE back in line; rotated_at moves only when
-- the value changes. The db-seed entrypoint skips this file when the value is empty.
INSERT INTO "public"."callback_secret" (
    "id",
    "caller_service",
    "secret_hash",
    "status",
    "rotated_at",
    "created_at",
    "updated_at"
) VALUES (
    '${AWE_CALLBACK_SECRET_ID}',
    '${AWE_CALLBACK_CALLER_SERVICE}',
    '${AWE_CALLBACK_HMAC_SECRET}',
    'active',
    NOW(),
    NOW(),
    NOW()
)
ON CONFLICT ("id") DO UPDATE SET
    "caller_service" = EXCLUDED."caller_service",
    "secret_hash" = EXCLUDED."secret_hash",
    "rotated_at" = CASE
        WHEN EXCLUDED."secret_hash" IS DISTINCT FROM "callback_secret"."secret_hash" THEN NOW()
        ELSE "callback_secret"."rotated_at"
    END,
    "updated_at" = NOW();
