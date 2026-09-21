# OpenG2P Farmer Registry — ODK Connector Service & Ingestion Guide

This guide documents the complete end-to-end configuration for ingesting **ODK Central** submissions into the **OpenG2P Farmer Registry**, using the standard platform architecture: **ODK Central + OpenG2P Connector Service + MinIO Jinja2 Template + Partner API + Celery Worker**.

---

## 1. Architecture Overview & Data Flow

```
[ ODK Collect (Mobile App) ]
       │ (Field agents submit survey)
       ▼
[ ODK Central ] (OData API endpoint)
       │
       │ Polled by Celery Beat ("resolve_nav_links": true)
       ▼
[ OpenG2P Connector Service ] (:8050) ── Managed by ── [ Connector UI ] (:5173)
       │ (Wraps ODK payload with standard envelope)
       ▼ POST /partner/ingest_data  (Header: `partner-id: farmer-partner`)
[ OpenG2P Partner API ] (:8002) (Authenticates partner in master_data DB)
       │ (Stores raw payload & enqueues Celery task to Redis)
       ▼
[ Redis Broker ] (:6379)
       │
       ▼
[ Registry Celery Worker ]
       ├── 1. Classifies payload against data_models (`FARMER_ODK_MODEL`)
       ├── 2. Fetches Jinja2 template (`farmer_transform.j2`) from MinIO (:9000)
       ├── 3. Renders target intake structure (personal info, location, lands, crops, livestock)
       └── 4. Generates draft intake submission (`g2p_intake_form_submissions`)
       │
       ▼
[ Staff Portal UI ] (:3000) ── Staff reviews & approves intake submission
       │
       ▼
[ Permanent Farmer Registry ] (`g2p_register_farmers`, `g2p_register_lands`, etc.)
```

---

## 2. Directory Contents

| File / Folder | Purpose |
| :--- | :--- |
| **`odk/ATI_Farmers_Profile_ODK_Form_v2.xlsx`** | Official XLSForm workbook with trilingual support (Amharic, Afaan Oromo, English), Ethiopian calendar, repeat groups, and GPS. |
| **`odk/KebeleList.csv`** | Preloaded lookup dataset (~9,000+ Kebeles) attached as media in ODK Central. |
| **`odk/PrimaryCoopList.csv`** | Preloaded lookup dataset for Primary Cooperatives attached as media. |
| **`odk/templates/farmer_transform.j2`** | Jinja2 template uploaded to MinIO `templates` bucket for Celery Worker transformation. |
| **`odk/setup_farmer_odk_connector.sql`** | Database seeds to register `farmer-partner` and `FARMER_ODK_MODEL`. |
| **`odk/README.md`** | Detailed field mapping table from ODK questions to OpenG2P tables. |

---

## 3. Step-by-Step Setup Instructions

### Step 1: Upload Form to ODK Central
1. Log in to **ODK Central** as Administrator.
2. Select or create your project (e.g., `Farmer Registry`).
3. Click **New Form** and upload `odk/ATI_Farmers_Profile_ODK_Form_v2.xlsx`.
4. Go to the form's **Form Settings** -> **Media Files** tab and upload:
   - `KebeleList.csv`
   - `PrimaryCoopList.csv`
5. Click **Publish Form**.

### Step 2: Configure Database Seeds
Run the queries in `odk/setup_farmer_odk_connector.sql`:

1. **In `master_data` database**:
   ```sql
   INSERT INTO public.g2p_partners (partner_id, partner_mnemonic, keymanager_reference_id, is_active)
   VALUES ('farmer-partner', 'Farmer', 'farmer-key-ref', true)
   ON CONFLICT (partner_id) DO NOTHING;
   ```

2. **In `farmer` registry database**:
   ```sql
   INSERT INTO public.data_models (data_model_id, data_model_mnemonic, pattern_for_data_model, response_template_document_id, is_active)
   VALUES ('FARMER_ODK_MODEL', 'FARMER_ODK_MODEL', '$.body.header.sender_id=>^.*$', NULL, true)
   ON CONFLICT (data_model_id) DO NOTHING;

   INSERT INTO public.incoming_model_key_paths (key_path_id, data_model_id, key_path_for_message_id, key_path_for_sender, key_path_for_signature, key_path_for_signature_payload, is_list, key_path_for_list_elements)
   VALUES ('farmer_key_path', 'FARMER_ODK_MODEL', '$.body.header.message_id', '$.body.header.sender_id', '$.body.header.signature', '$.body.message', false, NULL)
   ON CONFLICT (key_path_id) DO NOTHING;
   ```

### Step 3: Upload Jinja2 Template to MinIO
The Celery Worker reads `farmer_transform.j2` from the MinIO `templates` bucket:

```bash
# 1. Alias your MinIO endpoint (adjust host/credentials if needed)
mc alias set myminio http://minio:9000 minioadmin minioadmin

# 2. Upload template
mc cp odk/templates/farmer_transform.j2 myminio/templates/farmer_transform.j2

# 3. Verify object exists
mc ls myminio/templates
```

### Step 4: Configure OpenG2P Connector Service
In the **OpenG2P Connector UI** (or via API):

1. **Source Configuration (`source_config_json`)**:
   Set `resolve_nav_links: true` to enable automatic expansion of ODK repeat groups (land, crops, livestock):
   ```json
   {
     "base_url": "https://odk.yourdomain.org",
     "project_id": 1,
     "form_id": "ATI_Farmers_Profile_ODK_Form_v2",
     "resolve_nav_links": true
   }
   ```

2. **Target Configuration**:
   - **Target Ingest URL:** `http://farmer-registry-partner-api:8002/partner/ingest_data`
   - **Partner ID:** `farmer-partner`

---

## 4. Verifying the Ingestion Pipeline

1. **Submit a Survey**:
   - Fill out and submit a registration via ODK Collect or trigger a poll in Connector UI (`Poll Now`).
2. **Check Database Intake Tables**:
   ```sql
   -- Verify Celery classification status
   SELECT ingest_id, data_model_id, transformation_status, ingestion_status, intake_form_submission_id
   FROM incoming_classified_data ORDER BY classified_date_time DESC LIMIT 1;

   -- Verify intake submission created
   SELECT submission_id, application_reference, approval_status, first_created_at
   FROM g2p_intake_form_submissions ORDER BY first_created_at DESC LIMIT 1;
   ```
3. **Review & Approve in Staff Portal**:
   - Open Staff Portal (`http://localhost:3000` or production domain).
   - Go to **Intake Forms** -> **Farmer Ingestion Intake**.
   - Open the pending submission. All sections (Personal Info, Location, Land, Crops, Livestock, Farm Inputs, Membership) will be populated.
   - Click **Approve** to commit the record to the permanent Farmer Registry tables (`g2p_register_farmers`, etc.).
