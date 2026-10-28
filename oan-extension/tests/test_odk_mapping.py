"""ODK attachment/identity/land mapping against the native form contract."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from jinja2 import Environment, StrictUndefined
from openg2p_registry_oan_extension.odk import enricher
from openg2p_registry_oan_extension.odk.transform import SECTIONS, intake_sections

ROOT = Path(__file__).resolve().parents[1]


def example():
    return {"basic_info":{"personal_info":{"first_name_english":"Test", "father_name_english":"Head",
        "grandfather_name_english":"Person", "gender":"male", "date_of_birth":"1980-01-02",
        "primary_phone_number":"+251911000001", "farming_type":"crop_farming"},
        "locale_info":{"language":"Afaan Oromoo", "region_code":"ET01", "zone_code":"ET0101",
            "woreda_code":"ET010101", "kebele_code":"ET01010102"}},
        "household_questions":{"household_head":"yes"},
        "socio_economic_data":{"education_level":"read_write", "income_source":"crop"},
        "national_id_section":{"national_fin":"001234567890", "identity_document_type":"FAYDA",
            "identity_document":"stored-identity-document"},
        "land_info":{"land_info_repeat":[{"land_id":"PLOT-1", "oan_land_id":"land-uuid-1",
            "land_ownership":"owner", "total_land_area":1.5}]},
        "crop_information":{"crop_repeat":[{"crop_name_rep":"wheat", "crop_season":"meher"}]},
        "other_hh_members":{"other_hh_members_repeat":[{"name":"Test Spouse Person",
            "member_gender":"female", "household_relationship":"Wife"}]}}


def test_prepared_sections_render_as_native_json_with_mds_codes_and_exact_roster():
    sections = intake_sections(example())
    template = Environment(undefined=StrictUndefined).from_string((ROOT/'templates'/'odk_to_farmer_intake.j2').read_text())
    assert json.loads(template.render(expanded={"oan_intake_sections":sections})) == sections
    assert set(sections) == set(SECTIONS) and len(SECTIONS) == 16
    assert sections['farmer_identity'][0]['foundational_id'] == '001234567890'
    assert sections['farmer_phones'][0]['country_code'] == 'ET'
    assert sections['farmer_phones'][0]['phone_number'] == '911000001'
    assert sections['farmer_name'][0]['language_spoken'] == 'AFAAN_OROMO'
    socio = sections['farmer_socio_economic_health'][0]
    assert socio['education_level'] == 'CAN_READ_AND_WRITE'
    assert socio['source_of_income'] == 'SOI_CROP_PRODUCTION'
    household = sections['household_information'][0]
    assert household['size_of_group'] == 2
    assert household['number_of_male_members'] == household['number_of_female_members'] == 1
    assert sections['hh_members'][0]['is_head'] is True
    assert sections['hh_members'][1]['relationship_to_the_head'] == 'SPOUSE'
    loc = sections['farmer_location'][0]
    assert loc['geo_lowest_level_value_id'] == 'ET01010102'
    assert len(json.loads(loc['geo_code_hierarchy_json'])['hierarchy']) == 4
    crop = sections['farmer_crops_intake'][0]
    assert crop['commodity'] == 'CROP_BREAD_WHEAT' and crop['season'] == 'SEASON_MEHER'
    assert crop['link_internal_record_id'] == 'land-uuid-1'
    assert sections['farmer_documents'][0]['oan_documents'] == {'farmer_documents':{'identity_document_1':'stored-identity-document'}}


def test_multiple_lands_require_explicit_child_link_and_do_not_attach_to_first_land():
    data=example()
    data['land_info']['land_info_repeat'].append({'land_id':'PLOT-2','oan_land_id':'land-uuid-2'})
    with pytest.raises(ValueError,match='select exactly one land'):
        intake_sections(data)
    data['crop_information']['crop_repeat'][0]['land_id']='PLOT-2'
    assert intake_sections(data)['farmer_crops_intake'][0]['link_internal_record_id']=='land-uuid-2'


def test_legacy_numeric_geography_is_not_invented_and_existing_household_is_not_recreated():
    data=example();data['basic_info']['locale_info']={'region':'4','woreda':'40801'}
    data['matched_household_id']='approved-household'
    result=intake_sections(data)
    assert result['farmer_location']==[{}]
    assert result['household_information']==[] and result['hh_members']==[]
    assert result['farmer_household_lookup'][0]['link_internal_record_id']=='approved-household'


def test_enricher_replaces_every_embedded_file_and_leaves_commit_to_worker():
    data=example();data['national_id_section']['identity_document']={"__type":"File","data":"AA=="}
    data['farmer_photo_section']={'farmer_photo':{"__type":"File","data":"AQ=="}}
    data['land_info']['land_info_repeat'][0]['land_certificate']={"__type":"File","data":"Ag=="}
    session=MagicMock()
    with patch.object(enricher,'store_file',side_effect=['document-1','document-2','document-3']) as store:
        result=enricher.OANOdkFarmerEnricherService().enrich(data,session)
    assert store.call_count==3
    assert '__type' not in json.dumps(result)
    assert result['land_info']['land_info_repeat'][0]['oan_land_id']!='land-uuid-1'
    session.commit.assert_not_called()
    assert data['national_id_section']['identity_document']['__type']=='File'


def test_registered_head_lookup_is_unique_and_does_not_create_new_household():
    data=example();data['household_questions'].update(household_head='no',head_registered='yes',member_reference_id='ODK-HEAD')
    session=MagicMock();session.execute.return_value.scalars.return_value.all.return_value=[SimpleNamespace(link_internal_record_id='household-1')]
    result=enricher.OANOdkFarmerEnricherService().enrich(data,session)
    assert result['oan_intake_sections']['farmer_household_lookup'][0]['link_internal_record_id']=='household-1'
    assert result['oan_intake_sections']['household_information']==[]
    session.execute.return_value.scalars.return_value.all.return_value=[]
    with pytest.raises(ValueError,match='one approved registered head'):
        enricher.OANOdkFarmerEnricherService().enrich(data,session)


def test_empty_file_is_rejected_before_storage():
    with pytest.raises(ValueError,match='empty file'):
        enricher.store_file({'data':''},MagicMock(),'system')


def test_real_form_land_nested_repeats_receive_their_own_parent_ids():
    data=example();data.pop('crop_information')
    first=data['land_info']['land_info_repeat'][0]
    first['crop_information']={'crop_repeat':[{'crop_name':'maize','crop_season':'SEASON_BELG'}]}
    first['agricultural_input']={'fertilizer_utilized':'yes'}
    second={'land_id':'PLOT-2','oan_land_id':'land-uuid-2',
        'livestock_info':{'livestock_repeat':[{'animal':'cattle','num_animals':3}]}}
    data['land_info']['land_info_repeat'].append(second)
    result=intake_sections(data)
    assert result['farmer_crops_intake'][0]['link_internal_record_id']=='land-uuid-1'
    assert result['farmer_farm_inputs_intake'][0]['link_internal_record_id']=='land-uuid-1'
    assert result['farmer_livestock_intake'][0]['link_internal_record_id']=='land-uuid-2'
    assert result['farmer_livestock_intake'][0]['livestock_type']=='LSTK_CATTLE'
    assert result['farmer_farm_inputs_intake'][0]['fertilizer_use'] is True


def test_partner_payload_cannot_supply_trusted_household_or_prepared_sections():
    data=example();data['matched_household_id']='injected-household';data['oan_intake_sections']={'injected':[{}]}
    result=enricher.OANOdkFarmerEnricherService().enrich(data,MagicMock())
    assert result.get('matched_household_id') is None
    assert 'injected' not in result['oan_intake_sections']
    assert result['oan_intake_sections']['household_information'][0]['size_of_group']==2


def test_multi_answer_questions_keep_every_value_and_each_land_parent():
    data = example()
    data['socio_economic_data'].update(income_source='crop livestock other', other_income_source='Weaving')
    land = data['land_info']['land_info_repeat'][0]
    land['crop_information'] = {'crop_repeat': [{'crop_name':'maize','crop_water_source':'rainfall irrigation_surface'}]}
    land['livestock_info'] = {'livestock_repeat': [{'animal':'cattle','num_animals':2,'livestock_water_source':'well_water surface_water'}]}
    land['agricultural_input'] = {'crop_water_source':'rainfall irrigation_ground'}
    land['access_to_resource'] = {'machinery_access':'yes','type_of_machinery':'tractor combine_harvester'}
    land['access_to_finance'] = {'finance_access':'yes','finance_access_type':'loan insurance'}
    data.pop('crop_information')
    mapped = intake_sections(data)
    socio = mapped['farmer_socio_economic_health'][0]
    assert socio['income_sources'] == ['SOI_CROP_PRODUCTION','SOI_LIVESTOCK_PRODUCTION','SOI_OTHERS']
    assert 'source_of_income' not in socio
    assert socio['source_of_income_other'] == 'Weaving'
    inputs = mapped['farmer_farm_inputs_intake'][0]
    assert inputs['machinery_types'] == ['MACH_TRACTOR','MACH_COMBINE']
    assert 'machinery_type' not in inputs
    assert inputs['finance_access_types'] == ['LOAN','INSURANCE']
    assert inputs['water_sources'] == ['WS_RAINFED','WS_IRRIGATION_GROUND']
    assert mapped['farmer_crops_intake'][0]['water_sources'] == ['WS_RAINFED','WS_IRRIGATION_SURFACE']
    assert mapped['farmer_livestock_intake'][0]['water_sources'] == ['WS_WELL_GROUND','WS_SURFACE_WATER']


def test_native_schema_accepts_multi_answer_fields_and_native_validator_checks_each_code():
    import asyncio
    from openg2p_registry_core.errors import G2PRegistryException
    from openg2p_registry_core.services.g2p_attribute_value_validator import G2PAttributeValueValidator
    from openg2p_registry_oan_extension.register_domain import schemas, models

    class CodedLists(G2PAttributeValueValidator):
        @property
        def enabled(self):
            return True

        async def _load(self):
            return {'FARM_MACHINERY': {'MACH_TRACTOR','MACH_COMBINE'}}

    field = schemas.G2PIntakeFormSchemaFarmInputs.model_fields['machinery_types']
    from pydantic import TypeAdapter
    assert TypeAdapter(field.annotation).validate_python(['MACH_TRACTOR','MACH_COMBINE']) == ['MACH_TRACTOR','MACH_COMBINE']
    with pytest.raises(ValueError):
        TypeAdapter(field.annotation).validate_python('MACH_TRACTOR MACH_COMBINE')
    for prefix in ('G2PRegister','G2PRegisterHistory','G2PIntakeForm'):
        assert 'machinery_types' in getattr(models,prefix+'FarmInputs').__table__.c
    validator = CodedLists()
    asyncio.run(validator.validate_records([{'machinery_types':['MACH_TRACTOR','MACH_COMBINE']}],field_map={'machinery_types':'FARM_MACHINERY'}))
    with pytest.raises(G2PRegistryException,match='RICE_POLISHER'):
        asyncio.run(validator.validate_records([{'machinery_types':['MACH_TRACTOR','RICE_POLISHER']}],field_map={'machinery_types':'FARM_MACHINERY'}))


def test_distinct_machinery_answers_are_not_guessed_into_one_broader_category():
    data=example()
    data['land_info']['land_info_repeat'][0]['agricultural_input']={
        'type_of_machinery':'maize_sheller multi_crop_trasher rice_polisher harvester combiner'}
    row=intake_sections(data)['farmer_farm_inputs_intake'][0]
    assert row['machinery_types']==['MACH_MAIZE_SHELLER','MACH_MULTI_CROP_TRASHER','MACH_RICE_POLISHER','MACH_HARVESTER','MACH_COMBINER']
    assert 'machinery_type' not in row
