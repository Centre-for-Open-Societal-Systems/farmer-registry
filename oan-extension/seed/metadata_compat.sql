-- OAN-owned metadata compatibility, before the unchanged native Farmer seed.
-- Keep the legacy UUID/UI so stored requests can still resolve their section.
-- The public intake_fr_farmer_crops ingestion key moves to the native section;
-- it is not renamed in incoming messages or transformations. No records,
-- pending requests, identity grants or geographic assignments are changed.
DO $section_compat$
BEGIN
  IF EXISTS (SELECT 1 FROM public.g2p_register_sections
      WHERE section_id = 'a7d69d0c-ed5b-4d78-b2b5-90dfe40c8aa2'
        AND section_mnemonic = 'intake_fr_farmer_crops') THEN
    IF EXISTS (SELECT 1 FROM public.g2p_register_sections
        WHERE section_id = 'a7d69d0c-ed5b-4d78-b2b5-90dfe40c8aa2'
          AND (register_id IS DISTINCT FROM 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd'
            OR section_register_id IS DISTINCT FROM '5fa096f8-ffdc-4b0a-ab16-9ca386c23310')) THEN
      RAISE EXCEPTION 'Legacy Farmer crop section ownership differs; review metadata mapping';
    END IF;
    IF EXISTS (SELECT 1 FROM public.g2p_register_sections
        WHERE section_mnemonic = 'oan_legacy_intake_fr_farmer_crops'
          AND section_id <> 'a7d69d0c-ed5b-4d78-b2b5-90dfe40c8aa2') THEN
      RAISE EXCEPTION 'Legacy Farmer crop alias is occupied; review metadata mapping';
    END IF;
    UPDATE public.g2p_register_sections
      SET section_mnemonic = 'oan_legacy_intake_fr_farmer_crops'
      WHERE section_id = 'a7d69d0c-ed5b-4d78-b2b5-90dfe40c8aa2'
        AND section_mnemonic = 'intake_fr_farmer_crops';
  END IF;
END;
$section_compat$;
