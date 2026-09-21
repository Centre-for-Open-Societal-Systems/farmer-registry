# ATI Farmer Registry — ODK Profiling Form (XLSForm v2)

This directory contains the official **XLSForm** and reference datasets for the **OpenG2P Farmer Registry** data collection, ported and aligned from the ATI Gen 1 Odoo implementation (`atifarmer`).

---

## 1. Directory Contents

| File | Type | Description |
| :--- | :--- | :--- |
| **`ATI_Farmers_Profile_ODK_Form_v2.xlsx`** | XLSForm Workbook | Complete ODK form with `survey`, `choices`, and `settings` sheets, fully translated into English, Amharic, and Afaan Oromo. |
| **`KebeleList.csv`** | Media Attachment | Preloaded Kebele lookup list (9,000+ Kebeles) used with ODK `select_one_from_file`. |
| **`PrimaryCoopList.csv`** | Media Attachment | Preloaded Primary Cooperative lookup list used with ODK `select_one_from_file`. |

---

## 2. Form Architecture & Structure

### A. Languages Supported
The form is tri-lingual with native script rendering:
1. **English (en)** — Default language
2. **Amharic (am)** — አማርኛ
3. **Afaan Oromo (om)** — Afaan Oromoo

### B. Logical Sections in `survey` Sheet

1. **`consent_form_section`**:
   - Captures informed consent for personal and agricultural data collection in English, Amharic, and Afaan Oromo.
2. **`household_questions`**:
   - `household_head` (Yes / No)
   - `member_registered` / `head_registered`
   - `relationship_to_head` / `relationship_with_head`
   - `member_reference_id`
3. **`national_id_section`**:
   - `national_id` (Do you have a National ID / Fayda ID?)
   - `national_uid` (Fayda UID)
   - `national_rid` (Fayda RID)
   - `other_id` (Voter ID, Kebele ID)
4. **`basic_info`**:
   - **`locale_info`**: `region`, `zone`, `woreda`, `kebele` (with cascading filtering and fallback to `other_*`), `language`
   - **`personal_info`**:
     - English Names: `first_name_english`, `father_name_english`, `grandfather_name_english`
     - Amharic Names: `first_name_amharic`, `father_name_amharic`, `grandfather_name_amharic`
     - Afaan Oromo / Other: `first_name_other`, `father_name_other`, `grandfather_name_other`
     - `gender`, `date_of_birth` (Gregorian), `date_of_birth_ec` (Ethiopian calendar), `age`
     - Phones: `has_personal_phone`, `primary_phone_number`, `secondary_phone_number`, `other_phone_number`
     - `email`, `farming_type`, `disability`, `is_psnp_user`
5. **`socio_economic_data`**:
   - `marital_status`, `education_level`, `income_source`, family demographics
6. **`membership`**:
   - `primary_cooperative`, `name_of_primary_cooperative` (from `PrimaryCoopList.csv`), `coop_union`, `farmer_cluster`, `primary_commodity`, `farmer_role`
7. **`land_info` (`land_info_repeat`)**:
   - Repeat group for parcels: `land_ownership` (`OWNED`, `RENTED`, `CROP_SHARING`), `total_land_area`, `land_id`, `land_certificate` (photo/image upload)
8. **`crop_information` (`crop_repeat`)**:
   - Repeat group for crops: `crop_name`, `crop_date`, `crop_water_source`
9. **`livestock_info` (`livestock_repeat`)**:
   - Repeat group for livestock: `animal`, `num_animals`, `livestock_water_source`
10. **`agricultural_input`**:
    - Fertilizer, pesticide, insecticide, improved seed utilization
11. **`access_to_resource` & `access_to_finance`**:
    - Machinery access, machinery types, financial access, finance types
12. **`other_farmers_in_hh` (`other_farmers_repeat`)**:
    - Repeat group allowing the household head to register additional household members in the same interview session.
13. **`farmer_location`**:
    - `location` (`geopoint`: latitude, longitude, altitude, accuracy in meters)
14. **System Metadata**:
    - `start_time`, `submission_time`, `today`, `deviceid`, `username`

---

## 3. Field Mapping to OpenG2P Gen 2 Farmer Registry Models

| ODK Field Name | Gen 2 Target Table | Gen 2 Column / Field | Description / Logic |
| :--- | :--- | :--- | :--- |
| `first_name_english` | `g2p_register_farmers` | `first_name` | Given name (Latin) |
| `father_name_english` | `g2p_register_farmers` | `middle_name` | Middle name (Latin) |
| `grandfather_name_english`| `g2p_register_farmers` | `last_name` | Family name (Latin) |
| `first_name_amharic` | `g2p_register_farmers` | `first_name_amh` | Amharic Given Name |
| `father_name_amharic`| `g2p_register_farmers` | `middle_name_amh` | Amharic Middle Name |
| `grandfather_name_amharic`| `g2p_register_farmers` | `last_name_amh` | Amharic Family Name |
| `first_name_other` | `g2p_register_farmers` | `first_name_om` | Afaan Oromo Given Name |
| `father_name_other` | `g2p_register_farmers` | `middle_name_om` | Afaan Oromo Middle Name |
| `grandfather_name_other`| `g2p_register_farmers` | `last_name_om` | Afaan Oromo Family Name |
| `gender` | `g2p_register_farmers` | `gender` | `MALE` / `FEMALE` / `OTHERS` |
| `date_of_birth` | `g2p_register_farmers` | `birth_date` | Gregorian Date of Birth |
| `date_of_birth_ec` | `g2p_register_farmers` | `birth_date_ec` | Ethiopian Calendar Date |
| `household_head` | `g2p_register_farmers` | `is_household_head` | Boolean |
| `is_psnp_user` | `g2p_register_farmers` | `is_psnp_user` | Boolean |
| `national_uid` | `g2p_register_farmer_id_documents` | `value` (`id_type='UID'`) | Fayda National ID |
| `national_rid` | `g2p_register_farmer_id_documents` | `value` (`id_type='RID'`) | Fayda Registration ID |
| `farmer_reference_id` | `g2p_register_farmer_id_documents` | `value` (`id_type='FARMER_ODK_ACK_ID'`) | ODK Acknowledgement ID |
| `primary_phone_number`| `g2p_register_farmer_phones` | `phone_number` (`phone_type='PRIMARY'`) | Primary Phone |
| `secondary_phone_number`| `g2p_register_farmer_phones`| `phone_number` (`phone_type='SECONDARY'`) | Secondary Phone |
| `region` | `g2p_register_farmers` | `region_name` | Region |
| `zone` | `g2p_register_farmers` | `zone_name` | Zone |
| `woreda` | `g2p_register_farmers` | `woreda_name` | Woreda |
| `kebele` | `g2p_register_farmers` | `kebele_name` | Kebele |
| `location` (lat) | `g2p_register_farmers` | `enumerator_latitude` | GPS Latitude |
| `location` (lon) | `g2p_register_farmers` | `enumerator_longitude`| GPS Longitude |
| `location` (alt) | `g2p_register_farmers` | `enumerator_altitude` | GPS Altitude |
| `location` (acc) | `g2p_register_farmers` | `enumerator_accuracy` | GPS Accuracy (meters) |
| `username` | `g2p_register_farmers` | `enumerator_user_id` | Enumerator User ID |
| `submission_time` | `g2p_register_farmers` | `data_collection_date` | Collection Date |
| `land_info_repeat` | `g2p_register_lands` | Multiple rows | `ownership_type`, `land_size`, `land_id`, `land_certificate` |
| `crop_repeat` | `g2p_register_crops` | Multiple rows | `commodity`, `season`, `planted_date` |
| `livestock_repeat` | `g2p_register_livestocks` | Multiple rows | `livestock_type`, `head_count` |
| `other_farmers_repeat` | `g2p_register_household_members` | Multiple rows | Registered household members |

---

## 4. How to Deploy to ODK Central

1. **Log in to ODK Central**:
   Access your ODK Central web interface (e.g. `https://odk.yourdomain.org`).
2. **Create/Open Project**:
   Select or create a project (e.g., `Farmer Registry Ethiopia`).
3. **Upload Form**:
   - Click **New Form**.
   - Select `ATI_Farmers_Profile_ODK_Form_v2.xlsx`.
4. **Upload Attachments (Media Files)**:
   - In the form's **Media Files** tab in ODK Central, upload:
     - `KebeleList.csv`
     - `PrimaryCoopList.csv`
5. **Publish Form**:
   Click **Publish Form** to make it available for download by field tablets running **ODK Collect**.
