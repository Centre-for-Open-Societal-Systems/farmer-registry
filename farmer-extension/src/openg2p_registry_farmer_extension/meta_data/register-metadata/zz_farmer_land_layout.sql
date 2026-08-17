-- Use a deterministic two-row layout for the Farmer Lands detail section.
-- A single full-width vertical parent prevents the renderer from placing the
-- summary and child table beside one another, regardless of prior metadata.
UPDATE public.g2p_register_sections
SET section_ui_schema = $schema$
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
            },
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
          "panel-id": "panel_land_summary_row",
          "panel-title": "land_summary",
          "panel-column-span": 3,
          "panel-orientation": "horizontal"
        },
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
                  "widget": "select",
                  "column-key": "land_kebele",
                  "widget-type": "input",
                  "widget-label": "land_kebele",
                  "widget-data-path": "land_kebele",
                  "widget-data-source": {
                    "type": "api",
                    "method": "POST",
                    "service": "master-data",
                    "endpoint": "geo-level-values",
                    "level_id": "level-kebele",
                    "dependsOn": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.woreda_level_value_id",
                    "labelKey": "display_name",
                    "valueKey": "level_value_mnemonic"
                  }
                },
                {
                  "widget": "file",
                  "column-key": "certificate_storage_id",
                  "widget-type": "input",
                  "widget-label": "certificate_storage_id",
                  "widget-data-path": "certificate_storage_id",
                  "widget-data-options": {"accept": ".pdf,.jpg,.jpeg,.png,.webp", "multiple": false, "maxSize": 10485760}
                },
                {"widget":"checkbox","column-key":"certificate_provided","widget-type":"input","widget-label":"certificate_provided","widget-readonly":true,"widget-data-path":"certificate_provided"},
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
                    "type": "api",
                    "method": "POST",
                    "params": {"attribute_id": "MEANS_OF_ACQUISITION"},
                    "service": "attributes",
                    "endpoint": "values",
                    "labelKey": "value_display",
                    "valueKey": "value_id"
                  }
                },
                {"widget":"text","column-key":"remark","widget-type":"input","widget-label":"remark","widget-data-path":"remark"}
              ],
              "widget-data-add-label": "add_farm",
              "widget-data-operations": {"add": true, "edit": true, "remove": true}
            }
          ],
          "panel-id": "panel_land_table_row",
          "panel-column-span": 3,
          "panel-orientation": "vertical"
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
