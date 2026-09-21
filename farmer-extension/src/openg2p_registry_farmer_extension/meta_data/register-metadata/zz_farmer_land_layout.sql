-- Stack the Farmer Lands detail section as two full-width rows: the land
-- summary on top, the land records table underneath.
--
-- Nesting is deliberate. The widget library's PanelRenderer sizes a panel
-- that sits inside a VERTICAL parent by its "panel-column-span": with a span
-- it becomes a fixed span*200px block, without one it takes 100% of the row.
-- Inside a HORIZONTAL parent the same span becomes a grid-column span
-- instead. So the outer vertical wrapper keeps the rows stacked, each row is
-- an unspanned horizontal panel that fills the width, and only the leaf
-- vertical panels carry a span to divide that row's grid - the same
-- horizontal -> vertical(span 3) pair the Livestocks and Crops sections use.
--
-- Certificate Provided is derived on save from the uploaded certificate
-- (the land service sets it), so the Add/Edit dialog does not show it: the
-- column carries a "show" condition that is never true (notEmpty on a field
-- no row has; "equals" would not do, the library reads a boolean false as
-- equal to any non-truthy string). The table row still lists it --
-- conditions only govern the dialog in this widget library.
--
-- Land Kebele is free text (same in the intake copy in
-- g2p_register_sections.sql): it used to be a Master Data lookup of the
-- "kebele" level under the farmer's woreda, but a country pack need not carry
-- that level at all (the deployed ETH pack stops at woreda), and then the
-- dropdown could never list anything and the field was always null. The
-- portal pre-fills the box with the lowest place chosen in Location
-- (farmer-intake-rules.js) and the enumerator overtypes the kebele name.
UPDATE public.g2p_register_sections
SET section_ui_schema = $schema$
{
  "panels": [
    {
      "panels": [
        {
          "panels": [
            {
              "widgets": [
                    {
                      "widget": "number",
                      "widget-id": "total_land_owned_area",
                      "widget-type": "input",
                      "widget-label": "total_owned_land",
                      "widget-readonly": true,
                      "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.total_land_owned_area",
                      "widget-data-format": {"numericType": "decimal", "decimalPlaces": 3}
                    },
                    {
                      "widget": "number",
                      "widget-id": "total_land_rent_area",
                      "widget-type": "input",
                      "widget-label": "total_rented_land",
                      "widget-readonly": true,
                      "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.total_land_rent_area",
                      "widget-data-format": {"numericType": "decimal", "decimalPlaces": 3}
                    },
                    {
                      "widget": "number",
                      "widget-id": "total_land_crop_sharing_area",
                      "widget-type": "input",
                      "widget-label": "total_crop_sharing_land",
                      "widget-readonly": true,
                      "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.total_land_crop_sharing_area",
                      "widget-data-format": {"numericType": "decimal", "decimalPlaces": 3}
                    }
              ],
              "panel-id": "panel_land_summary_areas",
              "panel-column-span": 1,
              "panel-orientation": "vertical"
            },
            {
              "widgets": [
                    {
                      "widget": "number",
                      "widget-id": "total_land_area",
                      "widget-type": "input",
                      "widget-label": "total_land_area",
                      "widget-readonly": true,
                      "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.total_land_area",
                      "widget-data-format": {"numericType": "decimal", "decimalPlaces": 3}
                    },
                    {
                      "widget": "text",
                      "widget-id": "land_ownership",
                      "widget-type": "input",
                      "widget-label": "land_ownership",
                      "widget-readonly": true,
                      "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.land_ownership"
                    }
              ],
              "panel-id": "panel_land_summary_totals",
              "panel-column-span": 1,
              "panel-orientation": "vertical"
            }
          ],
          "panel-id": "panel_land_summary_row",
          "panel-title": "land_summary",
          "panel-orientation": "horizontal"
        },
        {
          "panels": [
            {
              "widgets": [
                    {
                      "widget": "dialog-table",
                      "widget-id": "lands_table",
                      "widget-type": "table",
                      "widget-label": "lands",
                      "widget-readonly": false,
                      "widget-data-path": "493153d5-07ef-4743-8efd-07f4099772b9.records",
                      "widget-data-visible-columns": ["land_id", "area_in_hectare", "land_ownership_type", "land_kebele", "certificate_storage_id", "certificate_provided"],
                      "widget-data-columns": [
                        {"widget":"text","column-key":"land_id","widget-type":"input","widget-label":"land_id","widget-data-path":"land_id"},
                        {
                          "widget": "number",
                          "column-key": "area_in_hectare",
                          "widget-type": "input",
                          "widget-label": "area_in_hectare",
                          "widget-data-path": "area_in_hectare",
                          "widget-data-format": {"allowSigned": false, "numericType": "decimal", "decimalPlaces": 3},
                          "widget-data-validation": {"min": 0.000001}
                        },
                        {
                          "widget": "select",
                          "column-key": "land_ownership_type",
                          "widget-type": "input",
                          "widget-label": "land_ownership_type",
                          "widget-data-path": "land_ownership_type",
                          "widget-data-source": {
                            "type": "static",
                            "options": [
                              {"label": "OWNER", "value": "OWNER"},
                              {"label": "TENANT", "value": "TENANT"},
                              {"label": "CROP_SHARE", "value": "CROP_SHARE"},
                              {"label": "FAMILY_GIFT", "value": "FAMILY_GIFT"}
                            ]
                          }
                        },
                        {
                          "widget": "text",
                          "column-key": "land_kebele",
                          "widget-type": "input",
                          "widget-label": "land_kebele",
                          "widget-readonly": false,
                          "widget-data-path": "land_kebele",
                          "widget-data-placeholder": "Kebele the land is in"
                        },
                        {
                          "widget": "file",
                          "column-key": "certificate_storage_id",
                          "widget-type": "input",
                          "widget-label": "certificate_storage_id",
                          "widget-data-path": "certificate_storage_id",
                          "widget-data-helptext": "certificate_file_hint",
                          "widget-data-options": {"accept": ".pdf,.jpg,.jpeg,.png,.webp", "multiple": false, "maxSize": 10485760}
                        },
                        {"widget":"checkbox","column-key":"certificate_provided","widget-type":"input","widget-label":"certificate_provided","widget-readonly":true,"widget-data-path":"certificate_provided","widget-data-options":{"action":"show","condition":{"field":"__never_set__","operator":"notEmpty"}}},
                        {"widget":"text","column-key":"soil_fertility","widget-type":"input","widget-label":"soil_fertility","widget-data-path":"soil_fertility"},
                        {
                          "widget": "select",
                          "column-key": "current_land_use",
                          "widget-type": "input",
                          "widget-label": "current_land_use",
                          "widget-data-path": "current_land_use",
                          "widget-data-source": {
                            "type": "static",
                            "options": [
                              {"label": "AGRICULTURAL", "value": "AGRICULTURAL"},
                              {"label": "RESIDENTIAL", "value": "RESIDENTIAL"},
                              {"label": "GRAZING", "value": "GRAZING"},
                              {"label": "FOREST", "value": "FOREST"}
                            ]
                          }
                        },
                        {
                          "widget": "select",
                          "column-key": "means_of_acquisition",
                          "widget-type": "input",
                          "widget-label": "means_of_acquisition",
                          "widget-data-path": "means_of_acquisition",
                          "widget-data-source": {
                            "type": "static",
                            "attribute_id": "MEANS_OF_ACQUISITION",
                            "options": [
                              {"label": "INHERITANCE", "value": "INHERITANCE"},
                              {"label": "DONATION_GIFT", "value": "DONATION_GIFT"},
                              {"label": "EXPROPRIATION", "value": "EXPROPRIATION"},
                              {"label": "RENTING_LEASING", "value": "RENTING_LEASING"},
                              {"label": "REALLOCATION", "value": "REALLOCATION"},
                              {"label": "DIVORCE_SETTLEMENT", "value": "DIVORCE_SETTLEMENT"}
                            ]
                          }
                        },
                        {"widget":"text","column-key":"remark","widget-type":"input","widget-label":"remark","widget-data-path":"remark"}
                      ],
                      "widget-data-add-label": "add_farm",
                      "widget-data-operations": {"add": true, "edit": true, "remove": true}
                    }
              ],
              "panel-id": "panel_land_table",
              "panel-column-span": 3,
              "panel-orientation": "vertical"
            }
          ],
          "panel-id": "panel_land_table_row",
          "panel-orientation": "horizontal"
        }
      ],
      "panel-id": "panel_land_layout_rows",
      "panel-column-span": 3,
      "panel-orientation": "vertical"
    }
  ],
  "section-id": "farmer_lands",
  "section-title": "farmer_lands",
  "section-editable": true,
  "section-column-span": 3
}
$schema$::json
WHERE section_id = 'farmer_farm_farm_details_section_01';
