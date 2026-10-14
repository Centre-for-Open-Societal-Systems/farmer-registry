-- Remove intake-form layout rows that earlier versions of this seed created and
-- later versions stopped shipping.
--
-- Every file in register-metadata/ is an upsert (INSERT ... ON CONFLICT DO
-- UPDATE). That makes re-seeding safe for rows the seed still carries, but it
-- has no way to express a row that was DELETED from the seed: dropping the line
-- from the .sql leaves the row sitting in every database that was seeded while
-- it was still there. The form is assembled from whatever
-- g2p_intake_form_ui_tab_sections holds, so those leftovers keep rendering.
--
-- That is what broke the farmer intake form on staging (2026-09-22): Crops,
-- Farm Inputs and Memberships each appeared twice. A database first seeded at
-- G2P-5402 (2f172d4) carries
--     tab_section_7 -> farmer_crop_crop_details_section_01        (order 60)
--     tab_section_8 -> farmer_farm_input_farm_input_details_...   (order 70)
--     tab_section_9 -> farmer_membership_membership_details_01    (order 80)
-- and G2R-73 (57ed71c) re-attached the same three sections under
-- tab_section_18/19 and e0506ad7 at orders 60/100/110 without removing the old
-- ids. A freshly seeded database (local compose) has the correct 15 sections and
-- none of these, which is why this only ever showed on long-lived environments.
--
-- The deletes are by explicit id. A `NOT IN (<the ids we keep>)` filter is the
-- tempting shorthand and is wrong here: the sections added by the zz_*.sql
-- overlays (farmer-photo-intake-tab-section-01,
-- farmer-phone-intake-tab-section-01,
-- farmer-household-information-intake-section-01) are not in this file, so such
-- a filter deletes the Farmer Photo, Phone Numbers and Household Information
-- sections on the next seed run. Listing what goes cannot do that.
--
-- Idempotent: a database that never had these rows deletes nothing. Keep new
-- entries here whenever a row is removed from a base seed file.

-- 1. Superseded sections of the farmer intake tab (a1a4d25a-...-72482721).
--    ts_* and tab_section_2 predate 2f172d4; 7/8/9 are the duplicates above.
DELETE FROM public.g2p_intake_form_ui_tab_sections
WHERE tab_section_id IN (
    'tab_section_2',
    'tab_section_7',
    'tab_section_8',
    'tab_section_9',
    'ts_1', 'ts_2', 'ts_3', 'ts_4', 'ts_5',
    'ts_6', 'ts_7', 'ts_8', 'ts_9', 'ts_10'
);

-- 2. The "Farmer Web Intake" form reversed by G2R-73 (fa8641a): a second farmer
--    form whose nine tabs exposed the same sections as the one that remains, so
--    staff picked between two entries in New Intake and the register held
--    records created under two form ids. Its tabs and tab-sections are layout
--    only and go unconditionally.
DELETE FROM public.g2p_intake_form_ui_tab_sections
WHERE tab_id IN (
    'd3f1c7a0-4b62-4e19-9c85-000000000010',
    'd3f1c7a0-4b62-4e19-9c85-000000000020',
    'd3f1c7a0-4b62-4e19-9c85-000000000030',
    'd3f1c7a0-4b62-4e19-9c85-000000000040',
    'd3f1c7a0-4b62-4e19-9c85-000000000050',
    'd3f1c7a0-4b62-4e19-9c85-000000000060',
    'd3f1c7a0-4b62-4e19-9c85-000000000070',
    'd3f1c7a0-4b62-4e19-9c85-000000000080',
    'd3f1c7a0-4b62-4e19-9c85-000000000090',
    'farmer_intake_form_tab'
);

DELETE FROM public.g2p_intake_form_ui_tabs
WHERE tab_id IN (
    'd3f1c7a0-4b62-4e19-9c85-000000000010',
    'd3f1c7a0-4b62-4e19-9c85-000000000020',
    'd3f1c7a0-4b62-4e19-9c85-000000000030',
    'd3f1c7a0-4b62-4e19-9c85-000000000040',
    'd3f1c7a0-4b62-4e19-9c85-000000000050',
    'd3f1c7a0-4b62-4e19-9c85-000000000060',
    'd3f1c7a0-4b62-4e19-9c85-000000000070',
    'd3f1c7a0-4b62-4e19-9c85-000000000080',
    'd3f1c7a0-4b62-4e19-9c85-000000000090',
    'farmer_intake_form_tab'
);

-- 3. The form definition itself, but only while nothing was ever submitted
--    through it. These metadata tables carry no foreign keys, so deleting a
--    definition that has submissions would not fail -- it would leave those
--    submissions pointing at a form that can no longer be rendered. Where such
--    submissions exist the row stays and the form remains visible: that is a
--    deliberate, reversible outcome to be resolved by migrating the
--    submissions, not by this seed.
DELETE FROM public.g2p_intake_form_definitions d
WHERE d.form_id = 'd3f1c7a0-4b62-4e19-9c85-6a1f2e0b7d41'
  AND NOT EXISTS (
      SELECT 1 FROM public.g2p_intake_form_submissions s
      WHERE s.form_id = d.form_id
  );
