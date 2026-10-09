"""The committed ODK form agrees with the pipeline and the transform.

odk/ATI_Farmers_Profile_ODK_Form_v2.xlsx is the XLSForm published on ODK
Central. If it drifts from the connector pipeline's form id, the connector
polls a form nobody fills; if it gains a photo question the transform does not
map, that photo never reaches the intake.
"""

import pathlib
import re

import pytest

openpyxl = pytest.importorskip("openpyxl")

REPO = pathlib.Path(__file__).resolve().parent.parent
ODK = REPO / "odk"
FORM = ODK / "ATI_Farmers_Profile_ODK_Form_v2.xlsx"
PIPELINE_SEED = REPO / "odk" / "seed_connector_pipelines.sql"
TRANSFORM = REPO / "odk" / "templates" / "farmer_transform.j2"
MEDIA_TYPES = {"image", "file", "audio", "video", "background-audio"}


def _sheet(name):
    workbook = openpyxl.load_workbook(FORM, read_only=True)
    rows = list(workbook[name].iter_rows(values_only=True))
    header = [str(cell).strip() if cell else "" for cell in rows[0]]
    return [dict(zip(header, row)) for row in rows[1:] if any(row)]


def test_form_id_is_the_one_the_pipeline_polls():
    form_id = _sheet("settings")[0]["form_id"]
    assert form_id == "farmer_profile"
    assert f'"form_id": "{form_id}"' in PIPELINE_SEED.read_text(encoding="utf-8")


def test_every_media_file_the_form_reads_is_committed():
    referenced = set()
    for row in _sheet("survey"):
        text = " ".join(str(row.get(col) or "") for col in ("type", "appearance", "calculation", "choice_filter"))
        referenced.update(re.findall(r"([\w.-]+\.csv)", text))
        referenced.update(f"{name}.csv" for name in re.findall(r"(?:search|pulldata)\(\s*'([\w.-]+)'", text))
    assert referenced, "expected the form to read its kebele and cooperative lists"
    missing = sorted(name for name in referenced if not (ODK / "media" / name).exists())
    assert not missing, f"media the form reads but odk/media lacks: {missing}"


def test_every_photo_question_is_mapped_by_the_transform():
    photos = {
        row["name"] for row in _sheet("survey")
        if row.get("type") and str(row["type"]).split()[0] in MEDIA_TYPES
    }
    assert photos == {"farmer_photo", "land_certificate", "hh_member_land_certificate"}
    template = TRANSFORM.read_text(encoding="utf-8")
    unmapped = sorted(name for name in photos if f"'{name}'" not in template)
    assert not unmapped, f"photo questions {unmapped} are not read by farmer_transform.j2"
