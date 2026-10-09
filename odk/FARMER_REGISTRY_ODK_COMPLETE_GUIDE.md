# OpenG2P Gen 2 Farmer Registry — ODK Central & Ingestion Architecture
## Complete Technical, Configuration & Operational Reference Guide

**Document Version:** 2.0.0  
**Release Status:** Official Production Guide  
**Target Audience:** Software Engineers, DevOps Engineers, Data Enumeration Teams, Registry Administrators  
**Date:** October 2026  

---

## 1. Executive Summary

This document serves as the authoritative, end-to-end technical specification and operational manual for ingesting farmer data collected via **ODK Central** into the **OpenG2P Gen 2 Farmer Registry**. 

Historically, farmer profiling in Gen 1 relied on Odoo modules and manual batch uploads. The OpenG2P Gen 2 platform modernizes this flow into a resilient, asynchronous, near-real-time event-driven architecture utilizing:
1. **ODK Collect & ODK Central**: Offline-first mobile data capture with cascading administrative lookups and multilingual questionnaire logic.
2. **OpenG2P Connector Service**: Decoupled, scheduled polling and webhook ingress engine with incremental checkpointing and deduplication.
3. **OpenG2P Partner API & Redis Broker**: Secure ingest envelope authentication and asynchronous task queue dispatching.
4. **Registry Celery Worker & MinIO Templates**: Payload classification, dynamic Jinja2 JSON schema transformation, and relational graph unnesting.
5. **Intake Staging & Approval Workflow Engine (AWE)**: Staging queues (`g2p_intake_form_*`), automated de-duplication against registers, four-eyes staff review, and final atomic persistence into core farmer registry tables.

---

## 2. End-to-End System Architecture

### 2.1 Architectural Flow Diagram

```
+----------------------------------------------------------------------------------+
|                              MOBILE FIELD LAYER                                  |
|   [ ODK Collect (Android App) ]                                                  |
|   - Offline Survey Completion (Tri-lingual: English, Amharic, Afaan Oromo)       |
|   - Cascading Geo Lookups: KebeleList.csv (9,000+ Kebeles)                       |
|   - Primary Coop Directory: PrimaryCoopList.csv                                  |
|   - GPS Geopoint Capture (Lat, Lon, Alt, Accuracy)                               |
+----------------------------------------+-----------------------------------------+
                                         |
                                         | HTTPS (Online Sync)
                                         v
+----------------------------------------------------------------------------------+
|                            ODK CENTRAL SERVER LAYER                              |
|   Server URL: https://odk.13.207.43.8.nip.io                                     |
|   Project ID: 13 ("Farmer Registry")                                             |
|   Form ID: farmer_profile ("Farmer Profiling Data Collection Form", v1.0.2)      |
|   - OData REST API: /v1/projects/13/forms/farmer_profile.svc/Submissions         |
|   - Repeat Groups: land_info_repeat, crop_repeat, livestock_repeat               |
+----------------------------------------+-----------------------------------------+
                                         |
                   +---------------------+---------------------+
                   |                                           |
   [Method A: Real-Time Webhook Push]           [Method B: Scheduled Poller Pull]
   ODK Central Webhook POST                     Connector Service (:8050)
   to /api/v1/farmer-registry/odk/webhook       Polls OData API every 30s
                   |                                           |
                   +---------------------+---------------------+
                                         |
                                         v
+----------------------------------------------------------------------------------+
|                       OPENG2P CONNECTOR SERVICE LAYER                            |
|   Container: farmer-registry-connector-api (:8050) / worker                      |
|   Pipeline: farmer-odk-pipeline-01                                               |
|   - Resolves OData Navigation Links (resolve_nav_links: true)                    |
|   - Maintains Polling Cursor & Boundary Timestamp in DB                          |
|   - Wraps Submission in OpenG2P Ingestion Envelope                               |
|   - Targets: POST http://farmer-registry-partner-api:8000/partner/ingest_data    |
+----------------------------------------+-----------------------------------------+
                                         |
                                         v
+----------------------------------------------------------------------------------+
|                     PARTNER INGESTION & CELERY WORKER                            |
|   1. Partner API (:8006 / :8000 internal) authenticates 'farmer-partner'         |
|   2. Stores raw payload & pushes task to Redis (:6387 / :6379 internal)          |
|   3. Registry Celery Worker classifies model: FARMER_ODK_MODEL                   |
|   4. Worker fetches Jinja2 template from MinIO: templates/farmer_transform.j2     |
|   5. Renders canonical intake structure:                                         |
|      - Normalizes phone numbers (removes +251, spaces, hyphens)                  |
|      - Strips whitespace from Fayda National UID / RID                           |
|      - Parses 4-coordinate GPS string into structured floats                     |
|      - Transforms repeat arrays for Land, Crops, Livestock, Inputs, Members      |
+----------------------------------------+-----------------------------------------+
                                         |
                                         v
+----------------------------------------------------------------------------------+
|                      INTAKE STAGING & APPROVAL (AWE)                             |
|   Staged Tables:                                                                 |
|   - g2p_intake_form_submissions (Approval Status: PENDING)                       |
|   - g2p_intake_form_farmers, g2p_intake_form_lands, g2p_intake_form_crops        |
|   Approval Workflow Engine (AWE): Starts workflow instance                       |
|   Staff Portal UI: http://localhost:3001/en/intake-form/farmer                   |
+----------------------------------------+-----------------------------------------+
                                         |
                                         | Staff Reviews & Clicks "Approve"
                                         v
+----------------------------------------------------------------------------------+
|                         PERMANENT FARMER REGISTRY                                |
|   - g2p_register_farmers (Functional ID: ET-FRM-XXXXX, Core Profile)             |
|   - g2p_register_farmer_phones (Primary & Secondary Phones)                      |
|   - g2p_register_farmer_id_documents (Fayda UID, RID, ODK Ack ID)                |
|   - g2p_register_lands (Land Parcels, Area in Ha, Land Tenure)                   |
|   - g2p_register_crops (Planted Crops linked to Land Parcels)                     |
|   - g2p_register_livestocks (Animal Counts & Production Systems)                 |
|   - g2p_register_farm_inputs & g2p_register_membership_details                   |
+----------------------------------------------------------------------------------+
```

---

## 3. Server & Infrastructure Inventory

### 3.1 ODK Central Server (Upstream Source)

| Parameter | Configuration Value |
| :--- | :--- |
| **Base URL** | `https://odk.13.207.43.8.nip.io` |
| **Admin Web Login** | `<odk-account-email>` |
| **Admin Password** | `<odk-account-password>` |
| **Project ID** | `13` (Display Name: `Farmer Registry`) |
| **Form XML ID** | `farmer_profile` |
| **Form Display Name** | `Farmer Profiling Data Collection Form` |
| **Published Version** | `1.0.2` |
| **Form State** | `open` |
| **OData Endpoint** | `https://odk.13.207.43.8.nip.io/v1/projects/13/forms/farmer_profile.svc/Submissions` |
| **App User 1 (Field Key)** | `Field_Officer_1` (Token: `CBgWA1NO$BWgO5vTjqPajzi2TlAmHUOeAf6CH9IYygRP$BvyotGIVlVA8bIHgseT`) |
| **App User 2 (Field Key)** | `QA Rohit` (Token: `u$FxbwULP7R0gjoHx1GrZQrj7OSMtv7lUtgAd6AswdavpdMqqm1A83F0$mzI!IDf`) |

### 3.2 Local Development Stack Inventory

| Service Component | Container Name | Host Port | Internal Port | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Connector UI** | `farmer-registry-connector-ui` | `5173` | `8080` | Web dashboard to monitor pipelines & runs |
| **Connector API** | `farmer-registry-connector-api` | `8050` | `8050` | Manages connectors, poll triggers, DLQ |
| **Connector Worker** | `farmer-registry-connector-worker` | N/A | N/A | Celery background daemon executing polls |
| **Partner API** | `farmer-registry-partner-api` | `8006` | `8000` | Ingestion endpoint receiving connector payloads |
| **Staff API** | `farmer-registry-staff-api` | `8001` | `8000` | Core Registry domain service |
| **Staff UI** | `farmer-registry-staff-ui` | `3001` | `3000` | Next.js Staff Portal for registry officers |
| **PostgreSQL 16** | `farmer-registry-postgres` | `5445` | `5432` | Relational database (farmer, connector, awe) |
| **Redis 7** | `farmer-registry-redis` | `6387` | `6379` | Task broker and distributed cache |
| **MinIO API** | `farmer-registry-minio` | `9002` | `9000` | Object storage hosting Jinja2 templates |
| **MinIO Console** | `farmer-registry-minio` | `9001` | `9001` | Object storage web management interface |
| **Keycloak IAM** | `farmer-registry-keycloak` | `8080` | `8080` | Identity and Access Management |
| **AWE API** | `farmer-registry-awe-api` | `8030` | `8000` | Approval Workflow Engine backend |

### 3.3 Deployed Server Environment Inventory (far.openg2p.test)

For testing against the deployed Kubernetes / Remote Server cluster (Namespace: `far`):

| Server Component | URL / Internal Endpoint | Purpose |
| :--- | :--- | :--- |
| **ODK Central Server** | `https://odk.13.207.43.8.nip.io` | Upstream cloud data collection server (Project 13, Form: `farmer_profile`) |
| **Server Connector Admin UI** | `https://connector-farmer-registry.far.openg2p.test` | Server dashboard for monitoring pipelines, runs, and DLQ |
| **Server Connector API** | `https://connector-farmer-registry.far.openg2p.test/connectors` | Server REST API managing pipelines and triggering manual polls |
| **Server Active Pipeline ID** | `9afff094f9a24a689fd53ce46af32cc4` | Live pipeline polling ODK Central every 30s |
| **Server Staff Portal UI** | `https://farmer-registry.far.openg2p.test` | Web UI for reviewing & approving farmer intake submissions |
| **Server Partner Ingest Target** | `http://farmer-registry-partner-api.far.svc.cluster.local/partner/ingest_data` | Internal Kubernetes cluster DNS target used by Connector Worker |

### 3.4 Data Routing & Architecture FAQs: Localhost vs. Remote Server

#### FAQ 1: Why did my colleague's submission from another state appear in my `localhost:3001`?
* **The Mechanism:** ODK Central (`https://odk.13.207.43.8.nip.io`) is a single, centralized cloud server hosted on AWS.
* **The Flow:**
  1. A colleague in another state or region fills out the ODK Collect form and submits it. The submission goes straight to the cloud ODK Central server under Project 13.
  2. You have your local development Docker environment running on your laptop. Inside your laptop, the `farmer-registry-connector-worker` container runs a scheduled polling loop every 30 seconds.
  3. Your local worker contacts the cloud ODK Central server over the internet, asks *"Are there any new submissions?"*, and downloads all new records (both your own test submission and your colleague's submission).
  4. Your local worker forwards them to your local database (`localhost:5445`) and local Staff Portal (`localhost:3001`).
* **Conclusion:** This confirms that your local connector service, database, Jinja2 template, and intake staging workflow are 100% operational and healthy.

#### FAQ 2: What happens if the Connector configuration on the server uses `localhost` instead of the internal cluster URL?
* **In Simple Terms:** In containerized environments (Docker and Kubernetes), every service/pod lives in its own isolated room (network namespace).
* **If `target_url` is set to `http://localhost:8000` on the server:**
  - The Connector Worker tries to find the Partner API inside its *own* pod.
  - Because the Partner API runs in a separate pod, the request fails immediately with `Connection Refused` or `Cannot reach host`.
* **The Correct Server Configuration:**
  - On the remote Kubernetes server (`far.openg2p.test`), the Connector MUST use the internal cluster DNS name:
    ```
    http://farmer-registry-partner-api.far.svc.cluster.local/partner/ingest_data
    ```
  - This allows the Connector pod to route requests directly to the Partner API pod across the internal Kubernetes network.

### 3.5 Remote Server Deployment Status & DevOps Action Checklist

The pipeline has been created and verified on the server:
* **Server Connector Admin UI:** `https://connector-farmer-registry.far.openg2p.test`
* **Configured Pipeline ID:** `9afff094f9a24a689fd53ce46af32cc4`
* **Status:** Active & Polling (successfully fetched 16 submissions from ODK Central).
* **Current Server Blocker:** When the server connector attempts to forward payloads to `http://farmer-registry-partner-api.far.svc.cluster.local/partner/ingest_data`, the Partner API returns `HTTP 500 Internal Server Error`.

#### Mandatory DevOps Action Items to Resolve the 500 Error:
To allow submissions to complete processing on the server, the DevOps team must execute the following 3 database seeds on the server cluster:

1. **In `master_data` PostgreSQL Database:**
   ```sql
   INSERT INTO public.g2p_partners (partner_id, partner_mnemonic, keymanager_reference_id, is_active)
   VALUES ('farmer-partner', 'Farmer', 'farmer-key-ref', true)
   ON CONFLICT (partner_id) DO NOTHING;
   ```
2. **In `farmer_registry_db` PostgreSQL Database:**
   ```sql
   INSERT INTO public.data_models (data_model_id, data_model_mnemonic, pattern_for_data_model, response_template_document_id, is_active)
   VALUES ('FARMER_ODK_MODEL', 'FARMER_ODK_MODEL', '$.body.header.sender_id=>^.*$', '1f0953d4-f0fb-4336-a126-4d0519a74ffc', true)
   ON CONFLICT (data_model_id) DO UPDATE SET response_template_document_id = EXCLUDED.response_template_document_id, is_active = true;

   INSERT INTO public.incoming_model_key_paths (key_path_id, data_model_id, key_path_for_message_id, key_path_for_sender, key_path_for_signature, key_path_for_signature_payload, is_list, key_path_for_list_elements)
   VALUES ('farmer_key_path', 'FARMER_ODK_MODEL', '$.body.header.message_id', '$.body.header.sender_id', '$.body.header.signature', '$.body.message', false, '')
   ON CONFLICT (key_path_id) DO UPDATE SET key_path_for_list_elements = EXCLUDED.key_path_for_list_elements;

   INSERT INTO public.incoming_model_semantic_patterns (semantic_pattern_id, data_model_id, register_id, intake_form_id, section_id, pattern_for_register, pattern_for_intake_form, pattern_for_section, key_path_for_business_payload, raw_payload_enricher_class)
   VALUES ('farmer_odk_semantic_pattern', 'FARMER_ODK_MODEL', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-8782382649', NULL, NULL, '$.body.header.sender_id=>^.*$', NULL, '$.body.message.payload', 'G2PDciFarmerCreateEnricherService')
   ON CONFLICT (semantic_pattern_id) DO UPDATE SET key_path_for_business_payload = EXCLUDED.key_path_for_business_payload;
   ```
3. **In Server MinIO Object Storage:**
   Ensure `odk/templates/farmer_transform.j2` is uploaded into the `templates` bucket of the server MinIO instance.
4. **Verification Step:**
   Once seeds are run, open `https://connector-farmer-registry.far.openg2p.test`, navigate to **Pipelines** ➔ **Runs**, and click **Replay** or trigger poll. Then verify that submissions appear in the Server Staff Portal at `https://farmer-registry.far.openg2p.test/en/intake-form/farmer`.

---

## 4. ODK Form Design & XLSForm Specifications

The data collection form (`odk/ATI_Farmers_Profile_ODK_Form_v2.xlsx`) contains 14 structured sections with full tri-lingual localization and preloaded CSV lookups.

### 4.1 Languages Supported
1. **English (`en`)** — Default reference language.
2. **Amharic (`am`)** — አማርኛ (Official federal working script).
3. **Afaan Oromo (`om`)** — Afaan Oromoo (Widely spoken regional language).

### 4.2 Preloaded Media Attachments
- **`KebeleList.csv`**: Contains over 9,000 Kebeles linked hierarchically by `region`, `zone`, and `woreda` codes. Uses ODK's `select_one_from_file` with `choice_filter` for responsive cascading selection on mobile devices without form latency.
- **`PrimaryCoopList.csv`**: Directory of registered Agricultural Primary Cooperatives and Unions.

### 4.3 Logical Form Sections

| # | Section Name | Questions Captured | Data Model Destination |
| :--- | :--- | :--- | :--- |
| **1** | `consent_form_section` | Informed consent agreement (`agree`/`disagree`) | Consent tracking |
| **2** | `household_questions` | `household_head`, `head_registered`, `relationship_to_head` | Farmer Household Demographics |
| **3** | `national_id_section` | `national_id` (Yes/No), `national_uid` (Fayda UID), `national_rid` (Fayda RID), `other_id` | National ID Registry Documents |
| **4** | `basic_info` / `locale_info` | `region`, `zone`, `woreda`, `kebele`, `language` | Administrative Geography |
| **5** | `basic_info` / `personal_info` | 3-part names in 3 scripts, `gender`, `date_of_birth` (GC), `date_of_birth_ec` (EC), `age`, `phone_number`, `primary_phone_number`, `secondary_phone_number`, `farming_type`, `disability` | Core Farmer Profile & Phones |
| **6** | `socio_economic_data` | `marital_status`, `education_level`, `income_source` | Socio-Economic Attributes |
| **7** | `membership` | `primary_cooperative`, `name_of_primary_cooperative`, `coop_union`, `farmer_cluster`, `primary_commodity` | Membership Details |
| **8** | `land_info_repeat` | **Repeat Group**: `land_ownership`, `total_land_area`, `land_id`, `land_certificate` (Photo) | Land Register (`g2p_register_lands`) |
| **9** | `crop_information` | **Repeat Group**: `crop_name`, `crop_date`, `crop_water_source` | Crop Register (`g2p_register_crops`) |
| **10** | `livestock_info` | **Repeat Group**: `animal`, `num_animals`, `livestock_water_source` | Livestock Register (`g2p_register_livestocks`) |
| **11** | `agricultural_input` | Fertilizer, pesticide, insecticide, improved seed utilization and volume | Farm Input Register |
| **12** | `access_to_resource` / `finance` | Machinery access (Tractor, Harvester), Savings, Credit, Loans | Socio-Economic Services |
| **13** | `other_hh_members_repeat` | **Repeat Group**: Other family members living in household | Household Members Register |
| **14** | `farmer_location` | `location` (`geopoint`: Latitude, Longitude, Altitude, Accuracy) | Farmer Surveyor GPS Coordinates |

---

## 5. Field Mapping & Transformation Matrix

The Celery Worker loads `odk/templates/farmer_transform.j2` from the MinIO `templates` bucket and applies transformations to convert raw ODK JSON into the OpenG2P Intake Schema.

| ODK Question Path | Target OpenG2P Table | Target Column Name | Type | Transformation / Conversion Logic |
| :--- | :--- | :--- | :--- | :--- |
| `personal_info/first_name_english` | `g2p_register_farmers` | `first_name` | String | Trims whitespace; title cases Latin given name. |
| `personal_info/father_name_english` | `g2p_register_farmers` | `middle_name` | String | Father's name (Ethiopian naming patronymic). |
| `personal_info/grandfather_name_english`| `g2p_register_farmers`| `last_name` | String | Grandfather's name. |
| `personal_info/first_name_amharic` | `g2p_register_farmers` | `first_name_amh` | String | UTF-8 Amharic given name (e.g. `ደስታ`). |
| `personal_info/father_name_amharic` | `g2p_register_farmers` | `middle_name_amh` | String | UTF-8 Amharic father name. |
| `personal_info/grandfather_name_amharic`| `g2p_register_farmers`| `last_name_amh` | String | UTF-8 Amharic grandfather name. |
| `personal_info/first_name_other` | `g2p_register_farmers` | `first_name_om` | String | Afaan Oromo given name. |
| `personal_info/gender` | `g2p_register_farmers` | `gender` | Enum | Mapped to uppercase: `MALE`, `FEMALE`, or `UNKNOWN`. |
| `personal_info/date_of_birth` | `g2p_register_farmers` | `birth_date` | Date | Extracted date part (`YYYY-MM-DD`) from Gregorian ISO string. |
| `personal_info/date_of_birth_ec` | `g2p_register_farmers` | `birth_date_ec` | Date | Preserves Ethiopian Calendar string (`YYYY-MM-DD`). |
| `household_questions/household_head` | `g2p_register_farmers` | `is_household_head`| Boolean| `true` if `yes`, `1`, or `true`. |
| `household_questions/is_psnp_user` | `g2p_register_farmers` | `is_psnp_user` | Boolean| Productive Safety Net Program beneficiary flag. |
| `national_id_section/national_uid` | `g2p_register_farmer_id_documents` | `value` (`id_type='UID'`) | String | Strips all spaces (e.g. `1234 5678 ...` -> `12345678...`). |
| `national_id_section/national_rid` | `g2p_register_farmer_id_documents` | `value` (`id_type='RID'`) | String | 29-digit Fayda Registration ID; stripped of spaces. |
| `farmer_reference_id` | `g2p_register_farmer_id_documents` | `value` (`id_type='FARMER_ODK_ACK_ID'`) | String | Unique ODK survey reference token. |
| `personal_info/primary_phone_number` | `g2p_register_farmer_phones` | `phone_number` | String | Strips `+251` or `251`, spaces, hyphens; typed as `PRIMARY`. |
| `personal_info/secondary_phone_number`| `g2p_register_farmer_phones` | `phone_number` | String | Normalizes secondary phone; typed as `SECONDARY`. |
| `locale_info/region` | `g2p_register_farmers` | `region_name` | String | Administrative Region code or name. |
| `locale_info/zone` | `g2p_register_farmers` | `zone_name` | String | Administrative Zone code or name. |
| `locale_info/woreda` | `g2p_register_farmers` | `woreda_name` | String | Administrative Woreda code or name. |
| `locale_info/kebele` | `g2p_register_farmers` | `kebele_name` | String | Administrative Kebele code or name. |
| `farmer_location/location` | `g2p_register_farmers` | `enumerator_latitude`, `longitude`, `altitude` | Float | Parses 4-part geopoint: `split(' ')` -> `[0]` Lat, `[1]` Lon, `[2]` Alt. |
| `land_info/land_info_repeat` | `g2p_register_lands` | Multiple | Array | Maps each parcel: `land_id`, `area_in_hectare`, `land_ownership_type`. |
| `crop_information/crop_repeat` | `g2p_register_crops` | Multiple | Array | Maps each crop: `commodity`, `planted_date`, `season`. Linked to primary land. |
| `livestock_info/livestock_repeat` | `g2p_register_livestocks` | Multiple | Array | Maps each animal: `livestock_type`, `head_count`, `livestock_system`. |

---

## 6. Database Seeds & Configuration Scripts

Before ODK Central data can be ingested, three databases must be configured:

### 6.1 Database: `master_data` (Register Partner)
```sql
INSERT INTO public.g2p_partners (partner_id, partner_mnemonic, keymanager_reference_id, is_active)
VALUES ('farmer-partner', 'Farmer', 'farmer-key-ref', true)
ON CONFLICT (partner_id) DO NOTHING;
```

### 6.2 Database: `farmer_registry_db` (Register Data Model & Key Paths)
```sql
-- 1. Register Data Model
INSERT INTO public.data_models (
    data_model_id, 
    data_model_mnemonic, 
    pattern_for_data_model, 
    response_template_document_id, 
    is_active
) VALUES (
    'FARMER_ODK_MODEL', 
    'FARMER_ODK_MODEL', 
    '$.body.header.sender_id=>^.*$', 
    '1f0953d4-f0fb-4336-a126-4d0519a74ffc', 
    true
) ON CONFLICT (data_model_id) DO UPDATE SET 
    pattern_for_data_model = EXCLUDED.pattern_for_data_model,
    response_template_document_id = EXCLUDED.response_template_document_id,
    is_active = true;

-- 2. Register Incoming Key Paths
INSERT INTO public.incoming_model_key_paths (
    key_path_id, 
    data_model_id, 
    key_path_for_message_id, 
    key_path_for_sender, 
    key_path_for_signature, 
    key_path_for_signature_payload, 
    is_list, 
    key_path_for_list_elements
) VALUES (
    'farmer_key_path', 
    'FARMER_ODK_MODEL', 
    '$.body.header.message_id', 
    '$.body.header.sender_id', 
    '$.body.header.signature', 
    '$.body.message', 
    false, 
    ''
) ON CONFLICT (key_path_id) DO UPDATE SET
    key_path_for_list_elements = EXCLUDED.key_path_for_list_elements;

-- 3. Register Incoming Model Semantic Pattern (Business Payload Mapping)
INSERT INTO public.incoming_model_semantic_patterns (
    semantic_pattern_id,
    data_model_id,
    register_id,
    intake_form_id,
    section_id,
    pattern_for_register,
    pattern_for_intake_form,
    pattern_for_section,
    key_path_for_business_payload,
    raw_payload_enricher_class
) VALUES (
    'farmer_odk_semantic_pattern',
    'FARMER_ODK_MODEL',
    'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd',
    'a1a4d25a-1cd4-4356-abac-8782382649',
    NULL,
    NULL,
    '$.body.header.sender_id=>^.*$',
    NULL,
    '$.body.message.payload',
    'G2PDciFarmerCreateEnricherService'
) ON CONFLICT (semantic_pattern_id) DO UPDATE SET
    key_path_for_business_payload = EXCLUDED.key_path_for_business_payload;
```

### 6.3 Database: `connector` (Register Pipeline Definition)
```sql
INSERT INTO connector_definitions (
    connector_id,
    name,
    platform,
    transport_type,
    enabled,
    paused,
    data_model_mnemonic,
    g2p_sender_id,
    g2p_register_mnemonic,
    source_config_json,
    auth_type,
    auth_secret_json,
    webhook_verifier
) VALUES (
    'farmer-odk-pipeline-01',
    'Farmer Registry - ODK Central Ingestion',
    'odk_central',
    'odk_central',
    true,
    false,
    'FARMER_ODK_MODEL',
    'farmer-partner',
    'Farmer',
    '{
        "base_url": "https://odk.13.207.43.8.nip.io",
        "project_id": 13,
        "form_id": "farmer_profile",
        "resolve_nav_links": true,
        "strict_incremental": false,
        "poll_interval_seconds": 30,
        "target_url": "http://farmer-registry-partner-api:8000/partner/ingest_data",
        "target_headers": {
            "partner-id": "farmer-partner",
            "Content-Type": "application/json"
        }
    }',
    'odk_session',
    '{
        "email": "<odk-account-email>",
        "password": "<odk-account-password>"
    }',
    'hmac_sha256'
)
ON CONFLICT (connector_id) DO UPDATE SET
    source_config_json = EXCLUDED.source_config_json,
    auth_secret_json = EXCLUDED.auth_secret_json,
    enabled = EXCLUDED.enabled;
```

### 6.4 MinIO Object Storage Setup
The Celery Worker expects the transformation template inside the `templates` bucket:
```bash
# Configure MinIO Client
mc alias set myminio http://localhost:9002 admin adminsecret

# Upload template
mc cp odk/templates/farmer_transform.j2 myminio/templates/farmer_transform.j2

# Verify
mc ls myminio/templates
```

---

## 7. Step-by-Step Manual Testing & Verification Protocol

### Method 1: The Automated 1-Click Python Test Script (Fastest)

Run the automated test script included in the repository:
```bash
python3 odk/test_odk_central_submission.py
```
**What happens behind the scenes:**
1. The script builds a valid OpenRosa XML survey instance with a randomized farmer name, national UID, and coordinates.
2. It POSTs the XML directly to `https://odk.13.207.43.8.nip.io/v1/key/<token>/projects/13/submission` with header `X-OpenRosa-Version: 1.0`.
3. It triggers an immediate poll on `http://localhost:8050/connectors/farmer-odk-pipeline-01/poll`.
4. The Connector Worker fetches the OData payload, resolves navigation links for repeat groups, and forwards it to Partner API `:8000`.
5. Celery Worker renders `farmer_transform.j2` and inserts a new draft submission into `g2p_intake_form_submissions`.

---

### Method 2: Manual cURL OpenRosa Submission

If you want to test raw HTTP submission to ODK Central from any terminal:

```bash
# 1. Create submission XML
cat << 'EOF' > /tmp/submission.xml
<?xml version="1.0" encoding="UTF-8" ?>
<data id="farmer_profile" version="1.0.2" xmlns:orx="http://openrosa.org/xforms">
  <consent_form_section><consent_form>agree</consent_form></consent_form_section>
  <household_questions><household_head>yes</household_head></household_questions>
  <national_id_section><national_uid>1122 3344 5566 7788</national_uid></national_id_section>
  <basic_info>
    <locale_info><region>2</region><zone>206</zone><woreda>20601</woreda><kebele>20601101001</kebele></locale_info>
    <personal_info>
      <first_name_english>Abebe</first_name_english>
      <father_name_english>Kebede</father_name_english>
      <grandfather_name_english>Bikila</grandfather_name_english>
      <gender>male</gender>
      <date_of_birth>1980-01-01</date_of_birth>
      <primary_phone_number>251911001122</primary_phone_number>
    </personal_info>
  </basic_info>
  <land_info>
    <land_info_repeat><land_ownership>owner</land_ownership><total_land_area>2.5</total_land_area><land_id>LND-1</land_id></land_info_repeat>
  </land_info>
  <crop_information>
    <crop_repeat><crop_name>wheat</crop_name><crop_date>2026-09-01</crop_date></crop_repeat>
  </crop_information>
  <meta><instanceID>uuid:manual-test-001</instanceID></meta>
</data>
EOF

# 2. POST to ODK Central OpenRosa endpoint
curl -k -i -X POST \
  -H "X-OpenRosa-Version: 1.0" \
  -F "xml_submission_file=@/tmp/submission.xml" \
  "https://odk.13.207.43.8.nip.io/v1/key/CBgWA1NO\$BWgO5vTjqPajzi2TlAmHUOeAf6CH9IYygRP\$BvyotGIVlVA8bIHgseT/projects/13/submission"

# 3. Trigger immediate Connector poll
curl -s -X POST http://localhost:8050/connectors/farmer-odk-pipeline-01/poll
```

---

### Method 3: Mobile Field Testing (ODK Collect on Android)

1. **Install App**: Download **ODK Collect** from Google Play Store or F-Droid.
2. **Scan Configuration**:
   - On a desktop, open [https://odk.13.207.43.8.nip.io](https://odk.13.207.43.8.nip.io) (Login: `<odk-account-email>` / `<odk-account-password>`).
   - Go to **Project 13 (`Farmer Registry`)** ➔ **App Users**.
   - Click the **QR Code** button next to `Field_Officer_1`.
   - On your phone, open ODK Collect, tap **Configure with QR code**, and scan the QR code.
3. **Download Forms & Media**:
   - Tap **Get Blank Form**.
   - Select **Farmer Profiling Data Collection Form**.
   - Ensure `KebeleList.csv` and `PrimaryCoopList.csv` download automatically.
4. **Collect & Submit**:
   - Tap **Fill Blank Form** ➔ complete all fields.
   - Tap **Save Form and Exit** ➔ **Send Finalized Form**.
   - The submission lands in ODK Central and is polled by the Connector within 30 seconds.

---

## 8. Verification & Review Workflows

### 8.1 Verifying In Connector Dashboard
Open `http://localhost:5173` in your web browser:
1. Click on **Pipelines** ➔ **`farmer-odk-pipeline-01`**.
2. Review the **Runs** table:
   - Status: `SUCCESS`
   - Attempt Count: `1`
   - Timestamp: Recent UTC time
3. In case of errors, inspect the **Last Error** column or navigate to the **Dead Letter Queue (DLQ)** tab.

### 8.2 Verifying In Database
Check the intake staging tables inside the PostgreSQL container:

```bash
# 1. Verify Intake Submission created
docker exec -i farmer-registry-postgres psql -U postgres -d farmer_registry_db -c "
SELECT submission_id, application_reference, approval_status, first_created_at 
FROM g2p_intake_form_submissions 
ORDER BY first_created_at DESC LIMIT 3;
"

# 2. Verify Staged Farmer Personal Info
docker exec -i farmer-registry-postgres psql -U postgres -d farmer_registry_db -c "
SELECT first_name, middle_name, last_name, first_name_amh, gender, birth_date, region_name, woreda_name 
FROM g2p_intake_form_farmers 
ORDER BY created_at DESC LIMIT 3;
"

# 3. Verify Staged Land & Repeat Groups
docker exec -i farmer-registry-postgres psql -U postgres -d farmer_registry_db -c "
SELECT land_id, land_ownership_type, area_in_hectare 
FROM g2p_intake_form_lands 
ORDER BY created_at DESC LIMIT 3;
"
```

### 8.3 Staff Review & Final Approval
1. Log in to the Staff Portal at `http://localhost:3001` with username `staff` and password `staff`.
2. Navigate to **Intake Forms** ➔ **Farmer Ingestion Intake**.
3. Locate the pending submission (e.g. `2026OCT05-XXXXXX`).
4. Click on the row to inspect all 8 intake tabs:
   - **Personal Information**: Trilingual names, birthdate, gender.
   - **Location**: Administrative cascade and surveyor GPS coordinates.
   - **Land**: Parcel IDs, tenure type, acreage.
   - **Crops & Livestock**: Commodities and animal headcounts.
   - **Farm Inputs & Membership**: Cooperative details and agricultural inputs.
5. Click **Approve**. The Approval Workflow Engine commits the submission to the permanent tables (`g2p_register_farmers`, `g2p_register_lands`, etc.).

---

## 9. Troubleshooting & Operational Runbook

| Symptom / Error | Root Cause | Remediation Step |
| :--- | :--- | :--- |
| **`HTTP 400: An expected header field (X-OpenRosa-Version) did not match`** | ODK Central OpenRosa submission endpoint requires protocol version header. | Include `-H "X-OpenRosa-Version: 1.0"` in your cURL or HTTP client request. |
| **`Server error 500: Server error for url 'http://farmer-registry-partner-api:8000/partner/ingest_data'`** | `farmer-partner` is missing in `master_data.g2p_partners` or Partner API is down. | Run SQL seed in `master_data` to register `farmer-partner`. Check `docker logs farmer-registry-partner-api`. |
| **`FARMER_ODK_MODEL transformation failed` in Celery logs** | MinIO is missing `farmer_transform.j2` or S3 credentials are invalid. | Run `mc cp odk/templates/farmer_transform.j2 myminio/templates/farmer_transform.j2`. Verify MinIO is healthy at `:9002`. |
| **Repeat groups (Land/Crops) are empty in Intake Form** | `resolve_nav_links` was set to `false` in connector definition. | Set `"resolve_nav_links": true` in `source_config_json` inside `connector_definitions`. |
| **Submissions stopped being fetched from ODK Central** | Polling cursor is stuck or corrupted in `poll_state_json`. | Reset the cursor via API: `curl -X POST http://localhost:8050/connectors/farmer-odk-pipeline-01/reset-cursor` or clear idempotency keys. |
| **`All connection attempts failed` in Connector Worker** | Network bridge cannot reach `https://odk.13.207.43.8.nip.io` or DNS resolution failed. | Check outbound internet access from Docker container: `docker exec -it farmer-registry-connector-worker curl -k -I https://odk.13.207.43.8.nip.io`. |
| **Fayda UID validation error during ingestion** | ODK Central stored UID with spaces (`1234 5678 ...`), violating OpenG2P 16-digit regex. | Handled automatically by `farmer_transform.j2` (`replace(' ', '')`). Ensure the latest template is uploaded. |

### 9.1 The ingestion log: "did my submission arrive?"

Every stage after the poll writes one JSON line per event to the `odk.ingest` log. The connector
(API and worker) writes `logs/odk-ingest.jsonl` under `/app` (setting `CONNECTOR_INGEST_LOG_FILE`;
empty = stdout only). The registry celery worker and the farmer extension write the same format to
`logs/odk-ingest.jsonl` in their working directory (`REGISTRY_EXTENSIONS_ODK_INGEST_LOG_FILE`).
Both also print to stdout, so `kubectl logs` shows them, and the file rotates at 20 MB (10 files).
A pod's file is lost when the pod is replaced; use the stdout copy in the cluster log stack for history.

Follow one submission by the ODK instance id (`source_event_id` is `<form_id>:<instance_id>` in the
connector, `instance_id` is the `uuid:...` part in the registry):

```sh
jq 'select(.source_event_id == "farmer_profile:uuid:1234" or .instance_id == "uuid:1234")' odk-ingest.jsonl
jq 'select(.severity != "INFO")' odk-ingest.jsonl      # everything that needs a look
```

Common fields: `ts`, `severity` (INFO / WARNING / ERROR), `stage`, `event`, `connector_id`,
`source_event_id`, `run_id`, `ingest_id`. Files appear by name, size and mime type only; the
submission, file contents and credentials are never logged.

| Stage | Event | Severity | Meaning / what to do |
| :--- | :--- | :--- | :--- |
| poll | `poll_started`, `poll_finished` | INFO (WARNING if some failed) | Counts per poll: `fetched`, `success`, `failed`. |
| poll | `poll_failed` | ERROR | The poll stopped (ODK unreachable, bad login, bad config). `error` has the reason. Submissions already processed are kept. |
| attachments | `attachment_embedded` | INFO | File downloaded and sent inline (`file_name`, `size_bytes`, `mime_type`). |
| attachments | `attachment_not_uploaded` | WARNING | ODK lists the file but the phone never uploaded it. The record goes without it. Ask the enumerator to sync. |
| attachments | `attachment_too_large` | WARNING | Over `attachment_max_bytes` (`size_bytes` vs `limit_bytes`). Raise the limit or retake smaller. |
| attachments | `attachment_download_failed` | WARNING | Central refused or timed out (`http_status`). A 403 means the connector's ODK user cannot read attachments. |
| attachments | `attachment_listing_failed` | WARNING | No attachment from this submission was fetched. Same checks as above. |
| attachments | `attachments_summary` | INFO / WARNING | Counts for the submission: listed, embedded, not_uploaded, too_large, download_failed. |
| attachments | `attachments_not_embedded` | INFO | `embed_attachments` is off for this pipeline. |
| map / validate / envelope / send | `map_failed`, `validate_failed`, `envelope_failed`, `send_failed` | ERROR | The run is FAILED and dead-lettered (`outcome`, `retryable`). `error` says why. Fix and replay from the connector DLQ. |
| result | `duplicate_ignored` | INFO | ODK sent a submission already ingested; nothing new was created. |
| send | `sent` | INFO | The Partner API accepted it (`correlation_id`). |
| enrich | `submission_received` | INFO / WARNING | Registry saw the submission: `files_embedded` and `files_name_only`. |
| enrich | `file_received` | INFO | A file arrived inline. |
| enrich | `file_missing` | WARNING | Only a file name arrived, so the file is saved without it. Match it with the connector's `attachment_*` events for the reason. |
| files | `file_stored` / `file_rejected` | INFO / ERROR | The photo or certificate (`purpose`: farmer_photo, land_certificate, member_certificate) was saved, or refused by the document profile (`error`: type or size). A refused file refuses the save. |
| ingest | `ingest_retry_scheduled` | WARNING | A worker attempt failed; it will try again (`attempt` of `max_attempts`). |
| ingest | `ingest_failed` | ERROR | Out of attempts. The row stays `FAILED` in `incoming_classified_data` with the reason in `ingestion_latest_error_code`. After the fix, set `ingestion_status` back to `PENDING`. |
| ingest | `ingest_succeeded` | INFO | The draft intake was created (`submission_id`). |

A submission with no `sent` and no `*_failed` event never left the connector: check `poll_failed`
and the checkpoint. One with `sent` but no `ingest_succeeded` or `ingest_failed` is still queued in
the registry worker, or failed before the ingest task (classify or transform): check the celery log
and `incoming_classified_data.transformation_status`.

---

## 10. Summary & Sign-off

This guide encapsulates the entire end-to-end operational and technical architecture for the OpenG2P Gen 2 Farmer Registry ODK integration. Both developers and field operations teams can utilize the endpoints, scripts, and verification procedures detailed above to ensure zero data loss, rigorous data validation, and seamless registration of Ethiopian smallholder farmers.
