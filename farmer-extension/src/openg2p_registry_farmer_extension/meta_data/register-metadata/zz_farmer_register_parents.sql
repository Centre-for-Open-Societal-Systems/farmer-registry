-- Crops, livestock and farm inputs belong to the FARMER, not to a land plot.
--
-- They were seeded with the Land register as master_register_id, so an intake
-- linked every crop/livestock/farm-input row to a land row, and the farmer's
-- Crops / Livestocks / Farm Inputs tabs (which list rows linked to the farmer,
-- like Lands and Phone Numbers) stayed empty after approval. The intake also
-- has no way to pick a plot: the parent lookup only offers LIVE lands, and the
-- lands of the same submission are not live yet. Gen1 kept these under the
-- farmer; so does this registry now.
--
-- g2p_register_definitions.sql is a plain INSERT, so an existing database
-- never sees a change to it; this UPDATE carries the change. Rows already
-- linked to a land are re-pointed at that land's farmer at staff-api boot
-- (app.py), which is where the other data repairs live.
UPDATE "public"."g2p_register_definitions"
SET "master_register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd'
WHERE "register_mnemonic" IN ('Crop', 'Livestock', 'FarmInputs')
  AND "master_register_id" IS DISTINCT FROM 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';
