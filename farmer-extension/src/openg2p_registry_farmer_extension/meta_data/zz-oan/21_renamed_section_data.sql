-- Data saved under the OAN sections' earlier ids follows them to their current
-- ids (10_sections.sql). Metadata is replaced by 22_retired_rows.sql; the rows
-- that point at a section by id (a record's documents, an intake's documents,
-- history, completion scores, change requests, verifications) are data and are
-- moved, never deleted. Every statement is a plain update keyed on the old id,
-- so a replay finds nothing to move and changes nothing; a fresh database has
-- no such rows.
DO $renamed_sections$
DECLARE
  pair record;
  tbl text;
  moved bigint;
BEGIN
  FOR pair IN SELECT * FROM (VALUES
      ('oan_farmer_personal_identification',   'farmer_identity'),
      ('oan_farmer_identity_verification',     'farmer_identity_verification'),
      ('oan_farmer_name',                      'farmer_personal_details'),
      ('oan_farmer_personal_details',          'farmer_personal_details'),
      -- The name section is merged into personal information.
      ('farmer_name',                          'farmer_personal_details'),
      ('oan_farmer_socio_economic_and_health', 'farmer_socio_economic_health'),
      ('oan_farmer_location',                  'farmer_location'),
      ('oan_farmer_photo',                     'farmer_photo'),
      ('oan_farmer_phones',                    'farmer_phones'),
      ('oan_farmer_documents',                 'farmer_documents'),
      ('oan_farmer_household_lookup',          'farmer_household_lookup'),
      ('oan_household_information',            'household_information'),
      ('oan_farmer_membership_details',        'farmer_membership'),
      ('oan_farmer_lands',                     'farmer_lands'),
      ('oan_farmer_land_summary',              'farmer_land_summary'),
      ('oan_farmer_crops',                     'farmer_crops'),
      ('oan_farmer_crops_intake',              'farmer_crops_intake'),
      ('oan_farmer_livestock',                 'farmer_livestock'),
      ('oan_farmer_livestock_intake',          'farmer_livestock_intake'),
      ('oan_farmer_farm_inputs',               'farmer_farm_inputs'),
      ('oan_farmer_farm_inputs_intake',        'farmer_farm_inputs_intake'),
      ('oan_farmer_enumerator',                'farmer_enumerator')
    ) AS v(old_id, new_id)
  LOOP
    -- Tables whose key does not include the section: the row simply moves.
    FOREACH tbl IN ARRAY ARRAY[
        'g2p_register_section_documents', 'g2p_register_document_history', 'g2p_intake_section_documents',
        'g2p_change_request_documents', 'g2p_register_change_requests',
        'g2p_register_verifications', 'g2p_completion_score_computation_queue',
        'g2p_register_history_farmers', 'g2p_register_history_households',
        'g2p_register_history_household_members', 'g2p_register_history_lands',
        'g2p_register_history_crops', 'g2p_register_history_livestocks',
        'g2p_register_history_farm_inputs', 'g2p_register_history_membership_details',
        'g2p_register_history_farmer_phones']
    LOOP
      IF to_regclass('public.' || tbl) IS NULL THEN CONTINUE; END IF;
      EXECUTE format('UPDATE public.%I SET section_id = %L WHERE section_id = %L', tbl, pair.new_id, pair.old_id);
      GET DIAGNOSTICS moved = ROW_COUNT;
      IF moved > 0 THEN
        RAISE NOTICE 'renamed section data: % rows of % moved from % to %', moved, tbl, pair.old_id, pair.new_id;
      END IF;
    END LOOP;
    -- The completion score is unique per record and section: a score already
    -- computed under the current id wins, and the stale one under the old id
    -- goes; otherwise the old score moves.
    IF to_regclass('public.g2p_register_section_completion_score') IS NOT NULL THEN
      DELETE FROM public.g2p_register_section_completion_score old
      WHERE old.section_id = pair.old_id
        AND EXISTS (SELECT 1 FROM public.g2p_register_section_completion_score cur
                    WHERE cur.register_id = old.register_id
                      AND cur.internal_record_id = old.internal_record_id
                      AND cur.section_id = pair.new_id);
      UPDATE public.g2p_register_section_completion_score
      SET section_id = pair.new_id WHERE section_id = pair.old_id;
      GET DIAGNOSTICS moved = ROW_COUNT;
      IF moved > 0 THEN
        RAISE NOTICE 'renamed section data: % completion scores moved from % to %', moved, pair.old_id, pair.new_id;
      END IF;
    END IF;
  END LOOP;
END $renamed_sections$;
