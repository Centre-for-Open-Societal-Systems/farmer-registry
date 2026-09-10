-- Farmer photo capture, in a section of its own.
--
-- There are two entry points for the same profile picture, and they belong to
-- different experiences:
--
--   * Register detail view -- the header section (zz_farmer_header_layout.sql)
--     already renders the picture at 120px with its own picker, writing the
--     embedded file into record_image_url.
--   * Intake form -- never renders the header section at all, so without a
--     widget of its own there is no way to capture a photo during intake;
--     staff could only add one after approval, from the detail view.
--
-- This section closes that gap for intake. It is deliberately attached to the
-- intake form tab ONLY: the widget lived in the Personal Information section
-- before, which is on both tabs, and that made "Farmer Photo" appear twice on
-- the detail view -- once here, once in the header -- two controls editing one
-- field. Do not add a g2p_register_ui_tab_sections row for it unless the
-- header widget's picker goes away first.
--
-- Both paths converge on the same column. The widget embeds the picked file as
-- a base64 blob in its value; G2PRegisterDomainServiceFarmer
-- _persist_embedded_profile_photo uploads it and swaps in a real document_id
-- for record_image_document_id on save (the same normalization the Land
-- certificate upload relies on) -- which is exactly what the header's
-- profile picture reads back. So a photo captured at intake shows up as the
-- farmer's profile picture on the detail view with no further wiring.
--
-- WHY header-section AND NOT file
-- -------------------------------
-- This section used the generic 'file' widget first. FileInputWidget renders
-- an "Upload File" button and the chosen file's *name* -- staff registering a
-- farmer could not see the photo they had just taken until after approval.
-- No other registered widget previews an image: ProfileWidget displays one but
-- has no picker, and the platform ships no dedicated photo widget.
--
-- header-section is the picker staff already know from the detail view: a
-- 120px avatar with an Upload/Delete overlay and a live preview of the pick.
-- Reusing it makes intake and detail the same control instead of two.
--
-- Its catch is that only the name and the completion-score ring are rendered
-- conditionally. Functional ID, Record Status, Status Reason and the
-- created/approved metadata rows render unconditionally, showing "-" where
-- there is no data -- and in an editable section, a status <select> and a
-- reason <input>, neither of which belongs mid-intake.
--
-- Omitting those keys from widget-data-path is what defuses that, not just
-- cosmetics: HeaderSectionWidget's findValue() and updateFieldValue() both
-- return early when a key has no path, so the widget reads nothing and, more
-- importantly, WRITES nothing for status or status reason. What is left is
-- empty chrome, hidden by docker/staff-ui/assets/intake-photo-widget.css --
-- scoped to this widget-id, so the detail header is untouched. Keep the
-- widget-id and that stylesheet's selectors in step.
INSERT INTO public.g2p_register_sections (
    register_id, section_id, section_register_id, is_core_section,
    section_mnemonic, section_description, documents_required,
    no_of_verifications_required, is_list, section_weightage,
    section_ui_schema, cr_auto_approve_for_bene_portal,
    cr_auto_approve_for_agent_portal, cr_auto_approve_for_staff_portal,
    cr_auto_approve_for_partner
) VALUES (
    'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd',
    'farmer_farmer_photo_section_01',
    -- The photo is a column on the Farmer register itself, not a child
    -- register, so this section reads/writes the same record as Personal
    -- Information does (cf. farmer_farmer_birth_information_section_01).
    'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd',
    FALSE, 'fr_farmer_photo', 'Farmer profile photo', FALSE,
    0, FALSE, 10,
    $schema$
    {
      "panels": [
        {
          "panels": [
            {
              "widgets": [
                {
                  "widget": "header-section",
                  "widget-id": "farmer-photo",
                  "widget-type": "group",
                  "widget-label": "farmer_photo",
                  "widget-required": false,
                  "widget-data-path": {
                    "image": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.record_image_document_id",
                    "imageUrl": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.record_image_url"
                  },
                  "widget-data-format": {"imageSize": 120}
                }
              ],
              "panel-id": "panel_farmer_photo",
              "panel-column-span": 1,
              "panel-orientation": "vertical"
            }
          ],
          "panel-id": "panel_farmer_photo_row",
          "panel-orientation": "horizontal"
        }
      ],
      "section-id": "farmer_photo",
      "section-title": "farmer_photo",
      "section-editable": true,
      "section-column-span": 3
    }
    $schema$::jsonb,
    FALSE, FALSE, FALSE, FALSE
)
ON CONFLICT (section_id) DO UPDATE SET
    section_register_id = EXCLUDED.section_register_id,
    is_list = EXCLUDED.is_list,
    section_description = EXCLUDED.section_description,
    section_ui_schema = EXCLUDED.section_ui_schema;

-- Straight after Personal Information (20), before Phone Numbers (22) -- the
-- photo reads as part of identifying the farmer, and that is where the widget
-- sat when it was still inside the Personal Information section.
INSERT INTO public.g2p_intake_form_ui_tab_sections (
    tab_section_id, tab_id, section_id, section_order
) VALUES (
    'farmer-photo-intake-tab-section-01',
    'a1a4d25a-1cd4-4356-abac-72482721',
    'farmer_farmer_photo_section_01', 21
)
ON CONFLICT (tab_section_id) DO UPDATE SET
    tab_id = EXCLUDED.tab_id,
    section_id = EXCLUDED.section_id,
    section_order = EXCLUDED.section_order;

-- Idempotent cleanup for benches seeded before this split: the widget used to
-- live in Personal Information, which is attached to farmer_farmer_tab, and a
-- re-seed onto an existing database leaves any stray attachment of this
-- section to the detail view behind.
DELETE FROM public.g2p_register_ui_tab_sections
WHERE section_id = 'farmer_farmer_photo_section_01';
