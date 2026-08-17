-- Keep the underlying geo hierarchy and address data intact, but present only
-- the Farmer-facing administrative labels and coordinates on the Location tab.
--
-- NOTE: this section also carries the Primary/Local Language panel and the
-- cascading geo-hierarchy dropdown (rather than flattened read-only text).
-- Both were dropped by an earlier version of this override and silently
-- disappeared on every reseed because this zz_ file loads after (and wins
-- over) g2p_register_sections.sql. Keep them here, not in the base file.
UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = $schema$
{
  "panels": [
    {
      "panels": [
        {
          "widgets": [
            {
              "widget": "geo-hierarchy",
              "widget-id": "farmer_geo_hierarchy",
              "widget-type": "input",
              "widget-label": "Location Hierarchy",
              "widget-required": false,
              "widget-data-path": {
                "value": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.geo_lowest_level_value_id",
                "hierarchy": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.geo_code_hierarchy_json"
              },
              "widget-geo-layout": {"columnSpan": 1},
              "widget-data-source": {
                "type": "api",
                "method": "POST",
                "service": "master-data",
                "levelsEndpoint": "get-all-g2p-geo-levels",
                "valuesEndpoint": "geo-level-values",
                "labelKey": "display_name",
                "valueKey": "level_value_id"
              }
            }
          ],
          "panel-id": "panel_geo_main",
          "panel-column-span": 1,
          "panel-orientation": "vertical"
        }
      ],
      "panel-id": "panel_administrative_location",
      "panel-orientation": "horizontal"
    },
    {
      "panels": [
        {
          "widgets": [
            {
              "widget": "number",
              "widget-id": "longitude",
              "widget-type": "input",
              "widget-label": "Geo Longitude",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.longitude",
              "widget-data-format": {
                "textAlign": "left",
                "allowSigned": true,
                "numericType": "decimal",
                "decimalPlaces": 7,
                "decimalSeparator": ".",
                "thousandSeparator": ","
              },
              "widget-data-validation": {
                "min": -180,
                "max": 180
              }
            },
            {
              "widget": "number",
              "widget-id": "latitude",
              "widget-type": "input",
              "widget-label": "Geo Latitude",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.latitude",
              "widget-data-format": {
                "textAlign": "left",
                "allowSigned": true,
                "numericType": "decimal",
                "decimalPlaces": 7,
                "decimalSeparator": ".",
                "thousandSeparator": ","
              },
              "widget-data-validation": {
                "min": -90,
                "max": 90
              }
            }
          ],
          "panel-id": "panel_geo_coordinates",
          "panel-title": "Location",
          "panel-column-span": 1,
          "panel-orientation": "vertical"
        }
      ],
      "panel-id": "panel_geo_coordinates_row",
      "panel-orientation": "horizontal"
    },
    {
      "panels": [
        {
          "widgets": [
            {
              "widget": "select",
              "widget-id": "language_spoken",
              "widget-type": "input",
              "widget-label": "primary_language",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.language_spoken",
              "widget-data-source": {
                "type": "api",
                "method": "POST",
                "params": {"attribute_id": "LANGUAGE"},
                "service": "attributes",
                "endpoint": "values",
                "labelKey": "value_display",
                "valueKey": "value_id"
              }
            },
            {
              "widget": "select",
              "widget-id": "local_language",
              "widget-type": "input",
              "widget-label": "local_language",
              "widget-readonly": false,
              "widget-required": false,
              "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.local_language",
              "widget-data-source": {
                "type": "api",
                "method": "POST",
                "params": {"attribute_id": "LANGUAGE"},
                "service": "attributes",
                "endpoint": "values",
                "labelKey": "value_display",
                "valueKey": "value_id"
              }
            }
          ],
          "panel-id": "panel_language",
          "panel-title": "language",
          "panel-column-span": 1,
          "panel-orientation": "vertical"
        }
      ],
      "panel-id": "panel_language_row",
      "panel-orientation": "horizontal"
    }
  ],
  "section-id": "farmer_location",
  "section-title": "farmer_location",
  "section-editable": true,
  "section-column-span": 2,
  "section-supporting-documents": []
}
$schema$::json
WHERE "section_id" = 'farmer_farmer_location_section_03';
