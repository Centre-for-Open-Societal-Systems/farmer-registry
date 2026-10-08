-- A spreadsheet may include household members. Their parent is a Household,
-- not the Farmer; include the existing household section so the normal intake
-- service can create/read/approve that parent in the same submission.
INSERT INTO public.g2p_intake_form_ui_tab_sections
    (tab_section_id, tab_id, section_id, section_order)
VALUES ('farmer_bulk_household_information',
        'a1a4d25a-1cd4-4356-abac-72482721',
        'farmer_household_household_information_section_01', 35)
ON CONFLICT (tab_section_id) DO NOTHING;
