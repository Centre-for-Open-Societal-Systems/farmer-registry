-- Ethiopian crop seasons.
--
-- The crop Season dropdown offered India's KHARIF / RABI / ZAYED, and the
-- sample data carried a third vocabulary (SUMMER / WINTER / MONSOON). Ethiopia
-- reports crop production by season as the CSA agricultural sample survey
-- does:
--
--   MEHER      main rains (kiremt), planted Jun-Sep -- the bulk of the harvest
--   BELG       short rains, planted Feb-May
--   IRRIGATED  dry season (bega), Oct-Jan, grown under irrigation
--   PERENNIAL  coffee, enset, chat, fruit -- no single season
--
-- The dropdown options themselves live in g2p_register_sections.sql. This
-- file carries their labels and moves rows already saved under the old codes,
-- so they show (and can be edited) under the new ones. Safe to re-run: after
-- the first pass no row holds an old code.

-- Labels. Other languages keep any translation they already have; where they
-- have none they fall back to the English word rather than MISSING_MESSAGE.
UPDATE "public"."registry_languages"
SET "domain_translation" = (
    jsonb_build_object(
        'MEHER', 'Meher',
        'BELG', 'Belg',
        'IRRIGATED', 'Irrigated'
    )
    || COALESCE("domain_translation"::jsonb, '{}'::jsonb)
);

-- Saved rows: the register, its history, and any intake draft still open.
-- Lower-case "Meher"/"Belg"/"Irrigated" came from generate_fr_bulk_sample.py.
UPDATE "public"."g2p_register_crops" SET "season" = CASE UPPER(TRIM("season"))
        WHEN 'MONSOON' THEN 'MEHER' WHEN 'KHARIF' THEN 'MEHER'
        WHEN 'SUMMER'  THEN 'BELG'  WHEN 'ZAYED'  THEN 'BELG'
        WHEN 'WINTER'  THEN 'IRRIGATED' WHEN 'RABI' THEN 'IRRIGATED'
        ELSE UPPER(TRIM("season")) END
WHERE UPPER(TRIM("season")) IN ('MONSOON', 'KHARIF', 'SUMMER', 'ZAYED', 'WINTER', 'RABI')
   OR "season" IN ('Meher', 'Belg', 'Irrigated');

UPDATE "public"."g2p_register_history_crops" SET "season" = CASE UPPER(TRIM("season"))
        WHEN 'MONSOON' THEN 'MEHER' WHEN 'KHARIF' THEN 'MEHER'
        WHEN 'SUMMER'  THEN 'BELG'  WHEN 'ZAYED'  THEN 'BELG'
        WHEN 'WINTER'  THEN 'IRRIGATED' WHEN 'RABI' THEN 'IRRIGATED'
        ELSE UPPER(TRIM("season")) END
WHERE UPPER(TRIM("season")) IN ('MONSOON', 'KHARIF', 'SUMMER', 'ZAYED', 'WINTER', 'RABI')
   OR "season" IN ('Meher', 'Belg', 'Irrigated');

UPDATE "public"."g2p_intake_form_crops" SET "season" = CASE UPPER(TRIM("season"))
        WHEN 'MONSOON' THEN 'MEHER' WHEN 'KHARIF' THEN 'MEHER'
        WHEN 'SUMMER'  THEN 'BELG'  WHEN 'ZAYED'  THEN 'BELG'
        WHEN 'WINTER'  THEN 'IRRIGATED' WHEN 'RABI' THEN 'IRRIGATED'
        ELSE UPPER(TRIM("season")) END
WHERE UPPER(TRIM("season")) IN ('MONSOON', 'KHARIF', 'SUMMER', 'ZAYED', 'WINTER', 'RABI')
   OR "season" IN ('Meher', 'Belg', 'Irrigated');
