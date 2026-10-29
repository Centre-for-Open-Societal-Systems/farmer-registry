"""OAN fields on the farmer extension's registers, declared once.

The registry platform's rule for a field whose column does not exist is to add
it to the register's model mixin, so the register, history and intake tables all
get it, and to its Pydantic schema, then show it through the section metadata.
The farmer extension is upstream and is not edited, so this package does the
same from outside: models/ appends each column to the three mapped classes, and
schemas/ subclasses the register and intake schemas under their own names,
which is how core finds them. Everything else about a field (label, widget,
validation, dropdown list) is seed metadata.

Every field the previous registries kept (Gen1 g2p_ati and the COSS farmer
registry) has a column here or upstream, so a migration loses nothing; the
README's migration map names the column for each.
"""

from datetime import date

from sqlalchemy import JSON, Boolean, Date, Numeric, String, Text

# register mnemonic -> {field: (column type, python type)}
OAN_FIELDS: dict[str, dict[str, tuple]] = {
    "Farmer": {
        # Multi-answer source questions use native JSON lists and MultiSelectWidget.
        # Legacy singular columns remain available for existing consumers.
        "income_sources": (JSON, list[str]),
        # An Ethiopian name is the person's, the father's and the grandfather's
        # name, which upstream's first, middle and last name hold in English.
        # The same three names in the farmer's own language (upstream's
        # language_spoken), in its script. Fayda fills them in when that
        # language is Amharic, and local_name_from_fayda then marks them.
        "first_name_local": (String, str),
        "middle_name_local": (String, str),
        "last_name_local": (String, str),
        "local_name_from_fayda": (Boolean, bool),
        # Productive Safety Net Programme beneficiary.
        "is_psnp_user": (Boolean, bool),
        # Ethiopian calendar twin of birth_date, derived from it.
        "birth_date_ec": (String, str),
        # A second, local or community language (LANGUAGE list).
        "local_language": (String, str),
        "is_household_head": (Boolean, bool),
        # Identifiers, as attributes of the farmer (OpenG2P's advice for the
        # migration): the Fayda FIN is upstream's foundational_id; the Fayda
        # registration id (RID) until a FIN is issued; the ODK Farmer ID; and
        # the Pula (Mavuno) ID, for a later Pula update to the same farmer.
        "rid": (String, str),
        "odk_farmer_id": (String, str),
        "pula_id": (String, str),
        # Who collected the record, where and when: taken from the submission
        # and the enumerator's device, never typed on the form.
        "enumerator_name": (String, str),
        "enumerator_user_id": (String, str),
        "data_collection_date": (Date, date),
        "enumerator_latitude": (Numeric(10, 7), float),
        "enumerator_longitude": (Numeric(10, 7), float),
        "enumerator_altitude": (Numeric(10, 2), float),
        "enumerator_accuracy": (Numeric(10, 2), float),
        # Derived from the farmer's active lands, in hectares.
        "total_land_area": (Numeric(16, 6), float),
        "total_land_owned_area": (Numeric(16, 6), float),
        "total_land_rent_area": (Numeric(16, 6), float),
        "total_land_crop_sharing_area": (Numeric(16, 6), float),
        "land_ownership": (String, str),  # OWNER, TENANT or HYBRID
        # Names of the units in geo_code_hierarchy_json, for lists and search.
        "region_name": (String, str),
        "zone_name": (String, str),
        "woreda_name": (String, str),
        "kebele_name": (String, str),
        # Asked by the previous registry.
        "has_national_id": (Boolean, bool),
        "is_farmer": (Boolean, bool),
        "farming_type": (String, str),  # FARMING_TYPE list
        # Kept from the previous registries, not asked on the form: the father's
        # own name (COSS kept it apart from the farmer's middle name), where the
        # record came from, the ODK submission, the duplicate flag and the
        # record's workflow state there.
        "father_first_name": (String, str),
        "father_middle_name": (String, str),
        "father_last_name": (String, str),
        "import_source": (String, str),
        "odk_instance_id": (String, str),
        "is_duplicated": (Boolean, bool),
        "legacy_state": (String, str),
        # The kind of document uploaded in each documents category; the files
        # are the record's documents (12_form_sections.sql).
        "identity_document_type": (String, str),
        "land_document_type": (String, str),
        "farmer_document_type": (String, str),
        "bank_document_type": (String, str),
        "representative_document_type": (String, str),
        "other_document_purpose": (String, str),
        "other_document_name": (String, str),
        # The outcome of the Fayda (eSignet) verification is core's: the
        # G2PRegisterAuthentication mixin on the Farmer model (models/).
    },
    "HouseholdMember": {
        "odk_member_id": (String, str),  # the ODK Member ID, as an attribute
        "birth_date_ec": (String, str),  # Ethiopian calendar twin of birth_date
        # A member's own land certificate, as COSS kept it.
        "certificate_storage_id": (Text, str),
        "certificate_provided": (Boolean, bool),
    },
    "Household": {
        "father_included": (Boolean, bool),
        "mother_included": (Boolean, bool),
        "other_farmer_in_household": (Boolean, bool),
    },
    "Land": {
        "land_id": (String, str),  # farmer-assigned or external parcel identifier
        "remark": (Text, str),
        "land_kebele": (String, str),
        # Derived: land_size in hectares, and whether a certificate is on file.
        "area_in_hectare": (Numeric(16, 6), float),
        "certificate_provided": (Boolean, bool),
    },
    "Crop": {
        "water_sources": (JSON, list[str]),
        "planted_date_ec": (String, str),  # Ethiopian calendar twin of planted_date
        "is_diseased": (Boolean, bool),
        "disease_type": (String, str),  # INFESTATION_AGENT list
    },
    "Livestock": {
        "water_sources": (JSON, list[str]),
        "gender": (String, str),  # attribute lookups
        "body_condition": (String, str),
        "production_type": (String, str),
        "collected_date": (Date, date),
        "collected_date_ec": (String, str),  # Ethiopian calendar twin of collected_date
        "season": (String, str),  # CROP_SEASON list
        "is_diseased": (Boolean, bool),
        "disease_type": (String, str),
    },
    "FarmInputs": {
        "water_sources": (JSON, list[str]),
        "livestock_water_sources": (JSON, list[str]),
        "machinery_types": (JSON, list[str]),
        "finance_access_types": (JSON, list[str]),
        # Upstream's water_source is the crops'; the previous registry asked the
        # livestock's too, and the irrigation and machinery used.
        "livestock_water_source": (String, str),  # WATER_SOURCE list
        "irrigation_type": (String, str),  # IRRIGATION_METHOD list
        "machinery_type": (String, str),  # FARM_MACHINERY list
        "finance_access_type": (String, str),
        "amount_fertilizer_utilized": (Numeric(12, 3), float),
        "amount_pesticide_utilized": (Numeric(12, 3), float),
        "amount_insecticide_utilized": (Numeric(12, 3), float),
        "amount_improved_seed_utilized": (Numeric(12, 3), float),
    },
    "MembershipDetails": {
        "primary_commodity": (String, str),  # attribute lookup: the cluster's focal commodity
    },
}
