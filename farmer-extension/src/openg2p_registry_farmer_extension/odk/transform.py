"""ODK source-field contract mapped to the current native Farmer intake schemas.

Pure mapping used by the registered enricher before the native Jinja template.
Unknown codes stay visible to native validation; no plausible demographics or
location codes are invented when a submission omits them.
"""
import json

from ..register_domain.name_rules import name_problems

SECTIONS = ("farmer_household_lookup", "farmer_identity", "farmer_name",
    "farmer_personal_details", "farmer_photo", "farmer_phones",
    "farmer_socio_economic_health", "household_information", "hh_members",
    "farmer_location", "farmer_lands", "farmer_crops_intake",
    "farmer_farm_inputs_intake", "farmer_livestock_intake",
    "farmer_membership", "farmer_documents")


def code(value, aliases=None, prefix=""):
    text = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    if not text:
        return None
    if aliases and text in aliases:
        return aliases[text]
    return text if not prefix or text.startswith(prefix) else prefix + text


def codes(value, aliases=None, prefix=""):
    """ODK select_multiple is space-separated text; never collapse its answers."""
    if value is None or value == "":
        return None
    values = value if isinstance(value, list) else str(value).split()
    return list(dict.fromkeys(code(item, aliases, prefix) for item in values if item))


def single(values):
    """Compatibility scalar exists only when the answer actually is singular."""
    return values[0] if values and len(values) == 1 else None


def boolean(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if str(value).strip().lower() in ("yes", "true", "1"):
        return True
    if str(value).strip().lower() in ("no", "false", "0"):
        return False
    raise ValueError("ODK yes/no answer: expected yes or no")


def day(value):
    return str(value).split("T")[0] if value else None


def number(value):
    return float(value) if value not in (None, "") else None


def rows(value):
    return value if isinstance(value, list) else []


def clean(record):
    return {k: v for k, v in record.items() if v is not None and v != ""}


CROPS = {"WHEAT":"CROP_BREAD_WHEAT", "BREAD_WHEAT":"CROP_BREAD_WHEAT",
    "MALT":"CROP_MALT_BARLEY", "NUG":"CROP_NOUG", "FALSE_BANANA":"CROP_ENSET",
    "KORERIMA":"CROP_KORARIMA", "UNKNOWN":"CROP_OTHER"}
LANGUAGES = {"AFAAN_OROMOO":"AFAAN_OROMO", "AFAAN_OROMO":"AFAAN_OROMO",
    "AMHARIC":"AMHARIC", "GURAGE":"GURAGIGNA", "HADIYYA":"HADIYYISA",
    "KAFA":"KAFI_NOONOO", "SIDAMO":"SIDAAMU_AFOO"}
WATER = {"RAINFALL":"WS_RAINFED", "IRRIGATION_GROUND":"WS_IRRIGATION_GROUND",
    "IRRIGATION_SURFACE":"WS_IRRIGATION_SURFACE", "WELL_WATER":"WS_WELL_GROUND",
    "WATER_HARVESTING":"WS_WATER_HARVESTING", "SURFACE_WATER":"WS_SURFACE_WATER"}
MACHINERY = {"TRACTOR":"MACH_TRACTOR", "PLANTER":"MACH_PLANTER",
    "COMBINE":"MACH_COMBINE", "COMBINE_HARVESTER":"MACH_COMBINE",
    "THRESHER":"MACH_THRESHER", "ROW_PLANTER":"MACH_ROW_PLANTER",
    "HARVESTER":"MACH_HARVESTER", "COMBINER":"MACH_COMBINER",
    "MULTI_CROP_TRASHER":"MACH_MULTI_CROP_TRASHER",
    "MAIZE_SHELLER":"MACH_MAIZE_SHELLER", "RICE_POLISHER":"MACH_RICE_POLISHER"}
INCOME = {"CROP":"SOI_CROP_PRODUCTION", "CROP_PRODUCTION":"SOI_CROP_PRODUCTION",
    "LIVESTOCK":"SOI_LIVESTOCK_PRODUCTION", "LIVESTOCK_PRODUCTION":"SOI_LIVESTOCK_PRODUCTION",
    "GOV_NGO":"SOI_GOVERNMENT_NGO_SUPPORT", "OTHER":"SOI_OTHERS"}
RELATIONSHIP = {"WIFE":"SPOUSE", "HUSBAND":"SPOUSE", "SON":"CHILD", "DAUGHTER":"CHILD",
    "OTHER":"OTHER_RELATIVE"}


def location(locale, gps):
    hierarchy = []
    for level in ("region", "zone", "woreda", "kebele"):
        value = locale.get(level + "_code")
        if value:
            hierarchy.append({"level_mnemonic": level.upper(), "level_value_id": str(value),
                "level_value_mnemonic": locale.get(level + "_name") or str(value)})
    record = {}
    if hierarchy:
        record.update(geo_lowest_level_value_id=hierarchy[-1]["level_value_id"],
            geo_code_hierarchy_json=json.dumps({"hierarchy": hierarchy}, ensure_ascii=False))
    # Legacy numeric ODK region/woreda values are deliberately not converted
    # to guessed MDS IDs. Native finalize explains the missing hierarchy.
    if isinstance(gps, dict):
        coords = gps.get("coordinates") or []
        values = [coords[1] if len(coords)>1 else None, coords[0] if coords else None,
            coords[2] if len(coords)>2 else None, (gps.get("properties") or {}).get("accuracy")]
    else:
        values = str(gps or "").split()
    record.update({field: number(value) for field, value in zip(
        ("latitude", "longitude", "altitude", "accuracy"), values) if value not in (None, "")})
    return record


def child_land(child, lands):
    selected = {str(child[key]).strip() for key in
        ('land_id', 'oan_land_id', 'crop_land_id', 'livestock_land_id', 'farm_input_land_id')
        if child.get(key) not in (None, '')}
    candidates = [land for land in lands if selected and all(
        value in (str(land.get('land_id') or '').strip(), str(land.get('oan_land_id') or '').strip())
        for value in selected)]
    if not selected and len(lands) == 1:
        candidates = lands
    if len(candidates) != 1 or not candidates[0].get("oan_land_id"):
        raise ValueError("ODK land: select exactly one land for each crop, livestock and farm-input row; resend with its land_id")
    return candidates[0]["oan_land_id"]


def intake_sections(d):
    basic = d.get("basic_info") or {}
    personal = basic.get("personal_info") or d.get("personal_info") or d.get("farmer_information") or {}
    locale = basic.get("locale_info") or d.get("locale_info") or {}
    questions = d.get("household_questions") or {}
    socio = d.get("socio_economic_data") or {}
    national = d.get("national_id_section") or d.get("identification") or {}
    membership = d.get("membership") or {}
    survey = d.get("survey_metadata") or {}
    system = d.get("__system") or {}
    is_head = boolean(questions.get("household_head"))
    household_id = d.get("matched_household_id")
    first = personal.get("first_name_english") or personal.get("first_name")
    middle = personal.get("father_name_english") or personal.get("middle_name")
    last = personal.get("grandfather_name_english") or personal.get("last_name")
    full_name = " ".join(str(x).strip() for x in (first,middle,last) if x)
    gender = code(personal.get("gender"), {"M":"MALE","F":"FEMALE"})
    fin = national.get("national_fin") or national.get("national_fan") or national.get("national_uid")
    fin = "".join(str(fin or "").split()) or None
    reference = d.get("farmer_reference_id_section") or d.get("farmer_reference_id") or {}
    reference = reference.get("farmer_reference_id") if isinstance(reference, dict) else reference
    output = {key: [] for key in SECTIONS}
    output[SECTIONS[4]] = [{}]
    output[SECTIONS[0]] = [clean({"is_household_head":is_head,"link_internal_record_id":household_id})]
    output[SECTIONS[1]] = [clean({"foundational_id":fin,"rid":national.get("national_rid"),
        "odk_farmer_id":reference,"has_national_id":boolean(national.get("national_id")),
        "import_source":"ODK", "odk_instance_id":(d.get("meta") or {}).get("instanceID") or d.get("__id"),
        "enumerator_name":survey.get("enumerator_name") or system.get("submitterName"),
        "enumerator_user_id":str(survey.get("enumerator_id") or system.get("submitterId") or ""),
        "data_collection_date":day(survey.get("survey_start") or system.get("submissionDate"))})]
    language = code(locale.get("language"), LANGUAGES)
    names = {"first_name":first,"middle_name":middle,"last_name":last,
        "first_name_local":personal.get("first_name_other") or personal.get("first_name_amharic"),
        "middle_name_local":personal.get("father_name_other") or personal.get("father_name_amharic"),
        "last_name_local":personal.get("grandfather_name_other") or personal.get("grandfather_name_amharic")}
    if problems := name_problems(names):
        raise ValueError("ODK name: " + "; ".join(problems))
    output[SECTIONS[2]] = [clean({"first_name":first,"middle_name":middle,"last_name":last,
        "first_name_local":personal.get("first_name_other") or personal.get("first_name_amharic"),
        "middle_name_local":personal.get("father_name_other") or personal.get("father_name_amharic"),
        "last_name_local":personal.get("grandfather_name_other") or personal.get("grandfather_name_amharic"),
        "language_spoken":language,"local_language":code(locale.get("local_language"), LANGUAGES)})]
    output[SECTIONS[3]] = [clean({"gender":gender,"birth_date":day(personal.get("date_of_birth")),
        "birth_date_ec":day(personal.get("date_of_birth_ec")),"estimated_age":personal.get("age"),
        "marital_status":code(socio.get("marital_status")),"has_personal_phone":boolean(personal.get("has_personal_phone") or personal.get("phone_number")),
        "farming_type":code(personal.get("farming_type"), {"CROP_FARMING":"CROP","LIVESTOCK_FARMING":"LIVESTOCK","MIXED_FARMING":"MIXED"}),
        "emails":[{"address":str(personal["email"]).strip(),"is_primary":True}] if personal.get("email") else None})]
    photo = (d.get("farmer_photo_section") or {}).get("farmer_photo") or personal.get("farmer_photo") or d.get("farmer_photo")
    if photo:
        output[SECTIONS[4]] = [{"record_image_document_id":photo}]
    for key, kind in (("primary_phone_number","PRIMARY"),("secondary_phone_number","SECONDARY"),("other_phone_number","OTHER")):
        phone = str(personal.get(key) or "").strip().replace(" ", "").replace("-", "")
        if phone.startswith("+251"):
            phone = phone[4:]
        elif phone.startswith("251"):
            phone = phone[3:]
        if phone:
            output[SECTIONS[5]].append({"phone_number":phone,"phone_type":kind,"country_code":"ET","is_primary":kind=="PRIMARY"})
    output[SECTIONS[6]] = [clean({"education_level":code(socio.get("education_level"),{"READ_WRITE":"CAN_READ_AND_WRITE"}),
        "income_sources":codes(socio.get("income_source"),INCOME),
        "source_of_income":single(codes(socio.get("income_source"),INCOME)),
        "source_of_income_other":socio.get("other_income_source"),
        "is_psnp_user":boolean(questions.get("is_psnp_user")),"disabled":boolean(personal.get("disability")),
        "disability_type":code(personal.get("disability_type")),"disability_severity":code(personal.get("disability_severity"))})]
    members = []
    if not household_id:
        if is_head:
            members.append(clean({"first_name":first,"middle_name":middle,"last_name":last,"gender":gender,
                "birth_date":day(personal.get("date_of_birth")),"is_head":True,"relationship_to_the_head":"SELF"}))
        raw_members = rows((d.get("other_hh_members") or {}).get("other_hh_members_repeat")) + \
            rows((d.get("other_farmers_in_hh") or {}).get("other_farmers_repeat")) + rows(d.get("other_farmers_repeat"))
        for member in raw_members:
            mp = (member.get("hh_member_basic_info") or {}).get("hh_member_personal_info") or {}
            parts = str(member.get("other_member_name_english") or member.get("name") or "").split()
            members.append(clean({"first_name":mp.get("hh_member_first_name_english") or (parts[0] if parts else None),
                "middle_name":mp.get("hh_member_father_name_english") or (parts[1] if len(parts)>1 else None),
                "last_name":mp.get("hh_member_grandfather_name_english") or (" ".join(parts[2:]) if len(parts)>2 else None),
                "gender":code(member.get("member_gender") or mp.get("hh_member_gender")),
                "birth_date":day(member.get("member_dob") or mp.get("hh_member_date_of_birth")),
                "is_head":boolean(member.get("is_head")) or False,
                "relationship_to_the_head":code(member.get("household_relationship") or mp.get("hh_member_relationship"),RELATIONSHIP),
                "odk_member_id":member.get("member_reference_id") or (member.get("hh_member_reference_id_section") or {}).get("hh_memeber_farmer_reference_id"),
                "certificate_storage_id":member.get("hh_member_land_certificate") or next((land.get("hh_member_land_certificate") for land in rows((member.get("hh_member_land_info") or {}).get("hh_member_land_info_repeat")) if land.get("hh_member_land_certificate")), None)}))
        if members:
            heads = [m for m in members if m.get("is_head")]
            head_name = full_name if is_head else " ".join(str(heads[0].get(k) or "") for k in ("first_name","middle_name","last_name")).strip() if heads else questions.get("household_head_name")
            output[SECTIONS[7]] = [clean({"household_head":head_name,"size_of_group":len(members),
                "number_of_male_members":sum(m.get("gender")=="MALE" for m in members),
                "number_of_female_members":sum(m.get("gender")=="FEMALE" for m in members),
                "other_land_owner":any((m.get("hh_member_land_info") or {}).get("hh_member_land_info_repeat") for m in raw_members),
                "other_farmer_in_household":boolean(((d.get("other_farmers_in_hh") or {}).get("other_farmers_in_hh_section") or d.get("other_farmers_in_hh") or {}).get("additional_farmers")),
                "father_included":boolean(questions.get("father_included")),"mother_included":boolean(questions.get("mother_included"))})]
    output[SECTIONS[8]] = members
    gps = d.get("farmer_location") or d.get("location") or {}
    output[SECTIONS[9]] = [location(locale, gps.get("location") if isinstance(gps,dict) else gps)]
    lands = rows((d.get("land_info") or {}).get("land_info_repeat")) or rows(d.get("land_info_repeat"))
    for land in lands:
        output[SECTIONS[10]].append(clean({"internal_record_id":land.get("oan_land_id"),"land_id":land.get("land_id"),
            "land_ownership_type":code(land.get("land_ownership")),"land_size":number(land.get("total_land_area") or land.get("land_area")),
            "unit":code(land.get("land_unit") or "HECTARE"),"certificate_storage_id":land.get("land_certificate"),
            "land_kebele":land.get("land_kebele"),"farming_type":code(land.get("farming_type") or personal.get("farming_type"),
                {"CROP_FARMING":"CROP","LIVESTOCK_FARMING":"LIVESTOCK","MIXED_FARMING":"MIXED"})}))
    crop_rows = list(rows((d.get("crop_information") or {}).get("crop_repeat")) or rows(d.get("crop_repeat")))
    animal_rows = list(rows((d.get("livestock_info") or {}).get("livestock_repeat")) or rows(d.get("livestock_repeat")))
    # The actual ATI form asks these in root sibling groups. Keep one input
    # row for those answers; child_land refuses ambiguous multi-land linkage.
    root_inputs = dict(d.get("agricultural_input") or {})
    root_inputs.update(d.get("access_to_resource") or {})
    root_inputs.update(d.get("access_to_finance") or {})
    for group, field in (("crop_information", "crop_water_source"), ("livestock_info", "livestock_water_source")):
        if (d.get(group) or {}).get(field) is not None:
            root_inputs[field] = d[group][field]
    if root_inputs and d.get('farm_input_land_id'):
        root_inputs['farm_input_land_id'] = d['farm_input_land_id']
    input_rows = [root_inputs] if root_inputs else []
    for land in lands:
        link = {"oan_land_id":land["oan_land_id"]}
        crop_rows += [dict(c, **link) for c in rows((land.get("crop_information") or {}).get("crop_repeat"))]
        animal_rows += [dict(a, **link) for a in rows((land.get("livestock_info") or {}).get("livestock_repeat"))]
        item = dict(land.get("agricultural_input") or {})
        item.update(land.get("access_to_resource") or {})
        item.update(land.get("access_to_finance") or {})
        for group, field in (("crop_information", "crop_water_source"), ("livestock_info", "livestock_water_source")):
            if (land.get(group) or {}).get(field) is not None:
                item[field] = land[group][field]
        if item:
            input_rows.append(dict(item, **link))
    for crop in crop_rows:
        output[SECTIONS[11]].append(clean({"link_internal_record_id":child_land(crop,lands),
            "commodity":code(crop.get("crop_name_rep") or crop.get("crop_name"),CROPS,"CROP_"),
            "planted_date":day(crop.get("crop_date")),"season":code(crop.get("crop_season"),prefix="SEASON_"),
            "water_sources":codes(crop.get("crop_water_source"),WATER),
            "end_use":"FOOD_HUMAN_CONSUMPTION"}))
    for farm_inputs in input_rows:
        record = {"link_internal_record_id":child_land(farm_inputs,lands)}
        for kind in ("fertilizer","pesticide","insecticide","improved_seed"):
            used = boolean(farm_inputs.get(kind+"_use") or farm_inputs.get(kind+"_utilized"))
            record[kind+"_use"] = used
            if used:
                record["amount_"+kind+"_utilized"] = number(farm_inputs.get(kind+"_amount"))
        record.update(water_sources=codes(farm_inputs.get("crop_water_source") or farm_inputs.get("water_source"),WATER),
            water_source=single(codes(farm_inputs.get("crop_water_source") or farm_inputs.get("water_source"),WATER)),
            livestock_water_sources=codes(farm_inputs.get("livestock_water_source"),WATER),
            livestock_water_source=single(codes(farm_inputs.get("livestock_water_source"),WATER)),
            access_to_machinery=boolean(farm_inputs.get("machinery_use") or farm_inputs.get("machinery_access") or farm_inputs.get("access_to_machinery")),
            machinery_types=codes(farm_inputs.get("machinery_type") or farm_inputs.get("type_of_machinery"),MACHINERY),
            machinery_type=single(codes(farm_inputs.get("machinery_type") or farm_inputs.get("type_of_machinery"),MACHINERY)),
            access_to_finance=boolean(farm_inputs.get("access_to_finance") or farm_inputs.get("finance_access")),finance_access_types=codes(farm_inputs.get("finance_access_type") or farm_inputs.get("finance")),
            finance_access_type=single(codes(farm_inputs.get("finance_access_type") or farm_inputs.get("finance"))),
            irrigation_type=code(farm_inputs.get("irrigation_type")))
        output[SECTIONS[12]].append(clean(record))
    for animal in animal_rows:
        output[SECTIONS[13]].append(clean({"link_internal_record_id":child_land(animal,lands),
            "livestock_type":code(animal.get("animal_rep") or animal.get("animal"),prefix="LSTK_"),
            "head_count":int(animal["num_animals"]) if animal.get("num_animals") not in (None,"") else None,
            "water_sources":codes(animal.get("livestock_water_source"),WATER),
            "livestock_system":code(animal.get("livestock_system")),"gender":code(animal.get("gender")),
            "season":code(animal.get("season"),prefix="SEASON_"),"collected_date":day(animal.get("collected_date")),
            "body_condition":code(animal.get("body_condition")),"production_type":code(animal.get("production_type"))}))
    output[SECTIONS[14]] = [clean({"is_primary_cooperative_member":boolean(membership.get("primary_cooperative")),
        "primary_cooperative_name":membership.get("other_primary_cooperative") if str(membership.get("name_of_primary_cooperative", "")).lower()=="other" else membership.get("name_of_primary_cooperative"),
        "is_cooperative_union_member":boolean(membership.get("coop_union")),"cooperative_union_name":membership.get("other_coop_union") if str(membership.get("name_of_coop_union") or membership.get("name_of_union") or "").lower()=="other" else membership.get("name_of_coop_union") or membership.get("name_of_union"),
        "is_farmer_cluster_member":boolean(membership.get("farmer_cluster")),"farmer_cluster_role":code(membership.get("farmer_role")),
        "primary_commodity":code(membership.get("primary_commodity"),CROPS,"CROP_")})]
    doc = national.get("identity_document") or national.get("identity_document_image")
    doc_type = code(national.get("identity_document_type"))
    output[SECTIONS[15]] = [clean({"identity_document_type":doc_type})]
    if doc:
        output[SECTIONS[15]][0]["oan_documents"] = {SECTIONS[15]:{"identity_document_1":doc}}
    return output
