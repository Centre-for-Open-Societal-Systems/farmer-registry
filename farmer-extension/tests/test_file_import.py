"""The native "Import from file" menu for the Farmer intake form: its own file-import data model whose key paths,
pass-through pattern and Jinja template take one flat CSV or Excel row (docs/file-import.md). The ODK model is not
touched."""
import json
import re
from pathlib import Path

import pytest
from jinja2 import Environment
from jinja2.exceptions import UndefinedError

ROOT = Path(__file__).resolve().parents[1] / 'src' / 'openg2p_registry_farmer_extension'
REPO = Path(__file__).resolve().parents[2]
META = ROOT / 'meta_data'

REGISTER = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd'
FORM = 'a1a4d25a-1cd4-4356-abac-8782382649'
CONFIG = 'eeb09070-dbde-56b4-b0a8-bb8acbb51c47'
MODEL = 'file_import_to_farmer_intake'
TEMPLATE = 'farmer_file_import_intake.j2'
SEED = '61_file_import_to_farmer_intake.sql'
REQUIRED = {'first_name', 'last_name', 'gender', 'is_household_head'}
BASE = {'first_name': 'Sample', 'last_name': 'Farmer', 'gender': 'MALE', 'is_household_head': 'yes'}
SECTIONS = ("farmer_household_lookup", "farmer_identity", "farmer_personal_details", "farmer_photo", "farmer_phones",
            "farmer_socio_economic_health", "household_information", "hh_members", "farmer_location", "farmer_lands",
            "farmer_crops_intake", "farmer_farm_inputs_intake", "farmer_livestock_intake", "farmer_membership",
            "farmer_documents")


def sql(folder, name):
    return (META / folder / name).read_text(encoding='utf-8')


def render(row):
    text = (ROOT / 'templates' / TEMPLATE).read_text(encoding='utf-8')
    return json.loads(Environment().from_string(text).render(expanded=row))


def header():
    return (REPO / 'import-templates' / 'farmer_intake_import_template.csv').read_text(encoding='utf-8').strip().split(',')


def test_import_configuration_has_a_fixed_id_and_points_at_the_form_own_data_model():
    text = sql('registry-configurations', 'g2p_registry_import_file_configurations.sql')
    assert re.search(rf"'{CONFIG}',\s*'{REGISTER}',\s*'{FORM}',\s*'{MODEL}',\s*'Farmer intake',", text)
    assert 'ON CONFLICT (import_file_configuration_id) DO UPDATE' in text
    assert 'https://oan.closedroominc.qzz.io/import-templates/' in text, 'the description links the template workbook'
    assert 'odk_to_farmer_intake' not in re.sub(r'^--.*$', '', text, flags=re.MULTILINE)
    assert f"('{FORM}','{REGISTER}'" in sql('register-metadata', 'g2p_intake_form_definitions.sql')


def test_data_model_key_paths_pattern_and_template_rows_are_upserts_on_the_import_envelope():
    seed = sql('zz-oan', SEED)
    assert f"('{MODEL}','FILE_IMPORT_TO_FARMER_INTAKE','$.headers.sender_id=>^Staff Portal$',NULL,TRUE)" in seed
    assert (f"('{MODEL}_key_path','{MODEL}','$.headers.message_id','$.headers.sender_id',"
            f"'$.headers.signature','$.body','FALSE','')") in seed
    assert re.search(rf"\('{MODEL}_pattern','{MODEL}','{REGISTER}','{FORM}',[^\n]*,'\$\.body',"
                     rf"'G2PPassThroughEnricherService'\)", seed)
    assert f"('{MODEL}_document','{TEMPLATE}','templates','{TEMPLATE}','seeder'" in seed
    assert f"('{MODEL}_template','{REGISTER}','{MODEL}','{MODEL}_document','FALSE'" in seed
    for key in ('"data_model_id"', '"key_path_id"', '"semantic_pattern_id"', '"document_id"', '"template_id"'):
        assert f'ON CONFLICT ({key}) DO UPDATE' in seed
    assert 'livestock' not in seed.lower()
    assert not re.search(r"odk_to_farmer_intake'?[,)]", re.sub(r'^--.*$', '', seed, flags=re.MULTILINE))


def test_pass_through_enricher_returns_the_row_unchanged_and_is_exported_by_name():
    # Loaded by path: the enricher package itself also imports the farmer models under their alias, which a plain
    # test run does not install. Core resolves the class by name on the package, so the export is checked as text.
    pytest.importorskip('openg2p_registry_core')
    import importlib.util

    package = ROOT / 'ingestion_pipeline' / 'enricher_services'
    spec = importlib.util.spec_from_file_location('farmer_pass_through', package / 'pass_through.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = {'first_name': 'Sample'}
    assert module.G2PPassThroughEnricherService().enrich(payload, None) is payload
    assert 'from .pass_through import G2PPassThroughEnricherService' in (package / '__init__.py').read_text(encoding='utf-8')


def test_blank_file_is_header_only_and_every_column_is_documented():
    raw = (REPO / 'import-templates' / 'farmer_intake_import_template.csv').read_bytes()
    assert b'\r' not in raw and len(raw.decode('utf-8').splitlines()) == 1, 'sample rows belong in openg2p-data'
    columns = header()
    assert len(columns) == len(set(columns))
    section = (REPO / 'docs/file-import.md').read_text(encoding='utf-8').split('## Farmer intake')[1].split('\n## ')[0]
    documented = dict(re.findall(r'^\| `(\w+)` \|[^|]*\|\s*(Yes|No) \|', section, re.MULTILINE))
    assert list(documented) == columns
    assert {c for c, required in documented.items() if required == 'Yes'} == REQUIRED


def test_every_column_is_read_and_the_sections_are_the_odk_intake_sections():
    full = {column: '' for column in header()}
    full.update(BASE, fayda_id='1234 5678 9012', middle_name='Middle', birth_date='1980-01-02 00:00:00',
                primary_phone_number='+251911000000', secondary_phone_number='0922000000', region='et04', zone='ET0404',
                latitude='9', longitude='38.7', land_id='PLOT-1', land_size='1.5', land_ownership_type='owner',
                education_level='primary', disabled='no', is_primary_cooperative_member='no',
                identity_document_type='fayda', marital_status='married', farming_type='crop')
    result = render(full)
    assert set(result) == set(SECTIONS)
    assert result['farmer_identity'] == [{'import_source': 'FILE_IMPORT', 'has_national_id': True,
                                          'foundational_id': '123456789012'}]
    personal = result['farmer_personal_details'][0]
    assert (personal['gender'], personal['birth_date'], personal['marital_status']) == ('MALE', '1980-01-02', 'MARRIED')
    assert [p['phone_number'] for p in result['farmer_phones']] == ['911000000', '0922000000']
    assert [p['is_primary'] for p in result['farmer_phones']] == [True, False]
    location = result['farmer_location'][0]
    assert location['geo_lowest_level_value_id'] == 'ET0404'
    assert [h['level_value_id'] for h in json.loads(location['geo_code_hierarchy_json'])['hierarchy']] == ['ET04', 'ET0404']
    land = result['farmer_lands'][0]
    assert re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-a[0-9a-f]{3}-[0-9a-f]{12}', land['internal_record_id'])
    assert (land['land_size'], land['unit'], land['land_ownership_type'], land['farming_type']) == (1.5, 'HECTARE', 'OWNER', 'CROP')
    assert result['farmer_documents'] == [{'identity_document_type': 'FAYDA'}]
    for section in ('farmer_crops_intake', 'farmer_farm_inputs_intake', 'farmer_livestock_intake'):
        assert result[section] == []


def test_a_head_starts_a_household_with_the_farmer_as_its_only_member():
    result = render({**BASE, 'gender': 'f', 'middle_name': 'Middle'})
    assert result['farmer_household_lookup'] == [{'is_household_head': True}]
    assert result['household_information'] == [{'household_head': 'Sample Middle Farmer', 'size_of_group': 1,
                                                 'number_of_male_members': 0, 'number_of_female_members': 1,
                                                 'other_land_owner': False}]
    assert result['hh_members'] == [{'first_name': 'Sample', 'last_name': 'Farmer', 'gender': 'FEMALE',
                                     'is_head': True, 'relationship_to_the_head': 'SELF', 'middle_name': 'Middle'}]
    other = render({**BASE, 'is_household_head': 'No'})
    assert other['farmer_household_lookup'] == [{'is_household_head': False}]
    assert other['household_information'] == [] and other['hh_members'] == []


def test_the_farmer_id_is_never_imported_and_no_land_without_land_columns():
    result = render({**BASE, 'farmer_id': 'FR-000000000001'})
    assert 'FR-000000000001' not in json.dumps(result)
    assert result['farmer_lands'] == [] and result['farmer_identity'][0]['has_national_id'] is False


@pytest.mark.parametrize('change,message', [
    ({'first_name': ''}, 'column first_name is required'),
    ({'gender': ''}, 'column gender is required'),
    ({'is_household_head': ''}, 'column is_household_head is required'),
    ({'is_household_head': 'maybe'}, 'column is_household_head must be yes or no'),
    ({'fayda_id': '12345'}, 'column fayda_id'),
    ({'birth_date': '02/01/1980'}, 'column birth_date must be a date'),
    ({'land_size': 'big'}, 'column land_size must be a number'),
    ({'household_size': '2.5'}, 'column household_size must be a whole number'),
    ({'latitude': '91', 'longitude': '38'}, 'column latitude must be between'),
    ({'latitude': '9'}, 'columns latitude and longitude must be given together'),
    ({'kebele': 'ET04040404'}, 'column kebele needs the level above it'),
    ({'gender': 'X'}, 'column gender must be a GENDER code, got X'),
    ({'marital_status': 'engaged'}, 'column marital_status must be a MARITAL_STATUS code, got ENGAGED'),
    ({'land_ownership_type': 'owned'}, 'column land_ownership_type must be a LAND_OWNERSHIP_TYPE code, got OWNED'),
    ({'land_unit': 'feet'}, 'column land_unit must be a LAND_SIZE_UNIT code'),
    ({'primary_commodity': 'teff'}, 'column primary_commodity must be a CROP_COMMODITY code, got TEFF'),
])
def test_a_value_the_template_cannot_read_fails_the_row_naming_the_column(change, message):
    with pytest.raises(UndefinedError, match=message):
        render({**BASE, **change})


# The import template workbook and the code lists: one source (scripts/import_templates/build_import_template.py).
BUILD = REPO / 'scripts' / 'import_templates' / 'build_import_template.py'
SNAPSHOT = REPO / 'import-templates' / 'farmer_intake_code_lists.json'


def builder():
    import importlib.util

    spec = importlib.util.spec_from_file_location('farmer_import_template_builder', BUILD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_code_lists_are_from_the_openg2p_data_commit_the_seed_pins():
    snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    dockerfile = (REPO / 'docker' / 'db-seed' / 'Dockerfile').read_text(encoding='utf-8')
    assert f"ARG OPENG2P_DATA_REF={snapshot['openg2p_data_ref']}" in dockerfile, 'rebuild: build_import_template.py --pack'
    module = builder()
    used = {spec[3] for spec in module.COLUMNS.values() if spec[2] == 'code'}
    assert set(snapshot['lists']) == used and all(snapshot['lists'][a] for a in used)


def test_every_coded_column_reads_that_list_in_the_section_metadata():
    seeds = ''.join(path.read_text(encoding='utf-8') for path in META.rglob('*.sql'))
    for column, spec in builder().COLUMNS.items():
        if spec[2] == 'code':
            assert re.search(rf"[\"']{spec[3]}[\"']", seeds), (column, spec[3])


def test_the_jinja_code_list_block_is_what_the_builder_generates():
    module = builder()
    lists = json.loads(SNAPSHOT.read_text(encoding='utf-8'))['lists']
    text = (ROOT / 'templates' / TEMPLATE).read_text(encoding='utf-8')
    assert module.BLOCK.search(text).group(2) == module.jinja_block(lists), 'rebuild: build_import_template.py --from-snapshot'


def test_builder_columns_are_the_csv_header_and_the_documented_required_columns():
    columns = builder().COLUMNS
    assert list(columns) == header()
    assert {c for c, spec in columns.items() if spec[1]} == REQUIRED


def test_workbook_has_the_header_dropdowns_and_the_code_lists():
    openpyxl = pytest.importorskip('openpyxl')
    book = openpyxl.load_workbook(REPO / 'import-templates' / 'farmer_intake_import_template.xlsx')
    assert book.sheetnames == ['Farmer intake', 'Code lists', 'Columns']
    sheet = book['Farmer intake']
    assert [c.value for c in sheet[1]] == header()
    assert not any(c.value not in (None, '') for row in sheet.iter_rows(min_row=2) for c in row),         'blank template: sample rows belong in openg2p-data'
    lists = json.loads(SNAPSHOT.read_text(encoding='utf-8'))['lists']
    codes = book['Code lists']
    for index in range(1, codes.max_column + 1, 2):
        attribute = codes.cell(row=1, column=index).value
        values = [codes.cell(row=r, column=index).value for r in range(2, codes.max_row + 1)]
        assert [v for v in values if v] == [code for code, _ in lists[attribute]], attribute
    formulas = {str(rule.sqref).split(':')[0]: rule.formula1 for rule in sheet.data_validations.dataValidation}
    gender = header().index('gender') + 1
    assert formulas[f'{openpyxl.utils.get_column_letter(gender)}2'].startswith("'Code lists'!")
    assert formulas[f"{openpyxl.utils.get_column_letter(header().index('disabled') + 1)}2"] == '"yes,no"'
    about = [row[0].value for row in book['Columns'].iter_rows(min_row=2) if row[0].value in columns_set()]
    assert about == header()


def columns_set():
    return set(header())


def test_the_code_lists_in_the_documentation_are_the_snapshot():
    lists = json.loads(SNAPSHOT.read_text(encoding='utf-8'))['lists']
    section = (REPO / 'docs/file-import.md').read_text(encoding='utf-8').split('\n## Code lists')[1].split('\n## ')[0]
    rows = dict(re.findall(r'^\| `(\w+)` \|[^|]*\| (.*) \|$', section, re.MULTILINE))
    assert set(rows) == set(lists)
    for attribute, values in lists.items():
        if len(values) >= 20:
            assert rows[attribute].startswith(f'{len(values)} '), attribute
        else:
            assert re.findall(r'`(\w+)`', rows[attribute]) == [code for code, _ in values], attribute


def test_a_minimal_row_sends_one_record_in_every_single_record_section():
    # The platform refuses an intake whose subject section holds no record ("Subject register section
    # 'farmer_documents' must contain exactly one record"), so these sections always carry one, as the
    # ODK intake sends them; an empty answer is an empty record.
    result = render({**BASE, 'is_household_head': 'no'})
    for section in ('farmer_household_lookup', 'farmer_identity', 'farmer_personal_details', 'farmer_photo',
                    'farmer_socio_economic_health', 'farmer_location', 'farmer_membership', 'farmer_documents'):
        assert len(result[section]) == 1, section
    assert result['farmer_documents'] == [{}]
