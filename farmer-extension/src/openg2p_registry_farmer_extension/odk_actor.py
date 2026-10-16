"""ODK collector attribution shared by intake and change-request ingestion.

This is a display/audit name supplied by ODK, never a Registry login or an
approval identity. The authenticated partner remains the source partner.
"""


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def ingestion_created_by(classified, enriched):
    # Other inbound models retain the platform's existing attribution.
    if classified.data_model_id != "FARMER_ODK_MODEL":
        return "system"
    data = enriched.enriched_data_json
    if not isinstance(data, dict):
        return "system"
    # The Farmer enricher normally returns the submission directly. Also
    # accept the connector's payload envelope, as the transform does.
    if isinstance(data.get("payload"), dict):
        data = data["payload"]
    survey = data.get("survey_metadata")
    survey = survey if isinstance(survey, dict) else {}
    system = data.get("__system")
    system = system if isinstance(system, dict) else {}
    # Match farmer_transform.j2: the named field collector takes precedence
    # over Central's uploading account, which may be a shared device.
    return (_text(survey.get("enumerator_name"))
            or _text(system.get("submitterName"))
            or "system")
