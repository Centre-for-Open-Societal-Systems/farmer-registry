-- Present Farmer-specific identity and workflow terminology in the detail
-- header. The core header defaults are intentionally left unchanged for other
-- registers such as Household.
UPDATE "public"."g2p_register_sections"
SET "section_ui_schema" = $schema$
{
  "panels": [
    {
      "panels": [
        {
          "widgets": [
            {
              "widget": "header-section",
              "widget-id": "registry-header",
              "widget-type": "group",
              "widget-data-path": {
                "name": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.record_name",
                "image": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.record_image_document_id",
                "imageUrl": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.record_image_url",
                "functionalId": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.functional_record_id",
                "status": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.state",
                "statusReason": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.record_status_reason",
                "createdBy": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.created_by",
                "createdAt": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.created_at",
                "lastApprovedBy": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.last_approved_by",
                "lastApprovedAt": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.last_approved_at"
              },
              "widget-labels": {
                "functionalId": "functional_record_id",
                "status": "state"
              },
              "widget-field-config": {
                "status": {
                  "data-source": {
                    "type": "static",
                    "options": [
                      {"value": "DRAFT", "label": "Draft"},
                      {"value": "PENDING", "label": "Pending"},
                      {"value": "APPROVED", "label": "Approved"},
                      {"value": "REJECTED", "label": "Rejected"},
                      {"value": "CANCELLED", "label": "Cancelled"}
                    ]
                  }
                }
              },
              "widget-data-format": {
                "imageSize": 120,
                "nameColor": "#ED7C22",
                "statusColors": {
                  "draft": "#6B7280",
                  "pending": "#D97706",
                  "approved": "#16A34A",
                  "rejected": "#DC2626",
                  "cancelled": "#6B7280"
                }
              }
            }
          ],
          "panel-id": "farmer_header_inside_panel",
          "panel-orientation": "vertical"
        }
      ],
      "panel-id": "farmer_header_outside_panel",
      "panel-orientation": "horizontal"
    }
  ],
  "section-id": "farmer_header",
  "section-title": "",
  "section-editable": true
}
$schema$::json
WHERE "register_id" = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd'
  AND "section_id" = '01425f4e-720e-4a4e-a0db-73f371ae2a07';
