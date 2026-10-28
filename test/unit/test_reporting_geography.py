"""Reporting labels require an authoritative, connected MDS hierarchy."""
import importlib.util
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

SPEC = importlib.util.spec_from_file_location('oan_reporting_geo',Path(__file__).resolve().parents[2]/'oan-extension/reporting/sync_geo_levels.py')
geo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(geo)


def levels():
    root, child = uuid4().hex, uuid4().hex
    return [{'level_id':child,'level_mnemonic':'District','parent_level_id':root},
        {'level_id':root,'level_mnemonic':'Province','parent_level_id':None}]


def test_empty_registry_does_not_change_authoritative_level_order():
    assert geo.ordered_levels(levels()) == [(1,'Province'),(2,'District')]


@pytest.mark.parametrize('case',['empty','duplicate','orphan','branch','cycle','missing-id'])
def test_incomplete_or_ambiguous_master_data_has_no_geography_fallback(case):
    rows = levels()
    if case=='empty': rows=[]
    if case=='duplicate': rows.append(rows[0].copy())
    if case=='orphan': rows[0]['parent_level_id']='missing-parent'
    if case=='branch': rows.append({'level_id':uuid4().hex,'parent_level_id':rows[1]['level_id'],'level_mnemonic':'Other'})
    if case=='cycle': rows[1]['parent_level_id']=rows[0]['level_id']
    if case=='missing-id': rows[0].pop('level_id')
    with pytest.raises(geo.GeographyUnavailable): geo.ordered_levels(rows)


@pytest.mark.skipif(not os.environ.get('OAN_REPORTING_MDS_SIMULATION_URL'),reason='Requires local Postman MDS simulation')
@pytest.mark.parametrize('case',['valid','token-down','api-down','refused','empty','wrong-client'])
def test_real_http_master_data_contract(case):
    url = os.environ['OAN_REPORTING_MDS_SIMULATION_URL']
    fixture = {'clientId':uuid4().hex,'clientSecret':uuid4().hex,'token':uuid4().hex,'levels':levels()}
    if case=='token-down': fixture['tokenUnavailable']=True
    if case=='api-down': fixture['unavailable']=True
    if case=='refused': fixture['refused']=True
    if case=='empty': fixture['levels']=[]
    with urlopen(Request(url+'/configure',data=json.dumps(fixture).encode(),headers={'Content-Type':'application/json'}),timeout=10) as response:
        assert response.status==200
    args=(url,url+'/token',fixture['clientId'],'wrong' if case=='wrong-client' else fixture['clientSecret'])
    if case=='valid':
        assert geo.fetch_levels(*args)==[(1,'Province'),(2,'District')]
    else:
        with pytest.raises(geo.GeographyUnavailable): geo.fetch_levels(*args)
