"""Native Farmer/OAN DDL and repeatable metadata in owned disposable PostgreSQL.

Does not connect to any existing database, import exports or run seed hooks.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]


def probe(host, mode):
    from sqlalchemy import create_engine, text
    sys.modules['openg2p_registry_extensions'] = importlib.import_module('openg2p_registry_oan_extension')
    importlib.import_module('openg2p_registry_staff_api.config').Settings.get_config()
    importlib.import_module('openg2p_registry_extensions.app').Initializer()
    from openg2p_fastapi_common.models import BaseORMModel
    engine = create_engine(f'postgresql+psycopg2://postgres@{host}/metadata_check')
    with engine.begin() as connection:
        connection.execute(text('CREATE EXTENSION IF NOT EXISTS pg_trgm'))
    BaseORMModel.metadata.create_all(engine)
    if mode == 'ddl':
        # Synthetic prior values exercise additive backfill across register,
        # history and intake, including intentionally empty/current JSON lists.
        from datetime import date, datetime
        from sqlalchemy import Boolean, Date, DateTime, Integer, JSON, Numeric, Uuid
        models = importlib.import_module('openg2p_registry_extensions.register_domain.models')
        with engine.begin() as connection:
            for mnemonic in ('Farmer','FarmInputs'):
                for index, prefix in enumerate(('G2PRegister','G2PRegisterHistory','G2PIntakeForm')):
                    table = getattr(models,prefix+mnemonic).__table__
                    values = {}
                    for column in table.columns:
                        if column.nullable or column.default is not None or column.server_default is not None:
                            continue
                        kind = column.type
                        if isinstance(kind,DateTime): value = datetime(2026,10,25)
                        elif isinstance(kind,Date): value = date(2026,10,25)
                        elif isinstance(kind,Boolean): value = False
                        elif isinstance(kind,(Integer,Numeric)): value = 1
                        elif isinstance(kind,JSON): value = {}
                        elif isinstance(kind,Uuid): value = str(uuid.uuid4())
                        else: value = ('fixture_'+column.name)[:getattr(kind,'length',None)]
                        values[column.name] = value
                    if mnemonic == 'Farmer':
                        values['source_of_income'] = 'SOI_CROP_PRODUCTION'
                    else:
                        values['machinery_type'] = 'MACH_TRACTOR'
                        if index == 1:
                            values['machinery_types'] = ['MACH_COMBINE','MACH_TRACTOR']
                        elif index == 2:
                            values['machinery_types'] = []
                    values['record_status'] = 'ACTIVE'
                    if mnemonic == 'Farmer' and index == 0:
                        values['internal_record_id'] = '00000000-0000-4000-8000-000000000001'
                    if mnemonic == 'FarmInputs' and index == 0:
                        values['link_internal_record_id'] = '00000000-0000-4000-8000-000000000002'
                        values['water_sources'] = ['WS_RAINFED','WS_IRRIGATION_SURFACE']
                    connection.execute(table.insert().values(**values))
                    if mnemonic == 'Farmer' and index == 0:
                        farmer = dict(values)
            for suffix, key, parent, extra in (
                ('Land','00000000-0000-4000-8000-000000000002',farmer['internal_record_id'],
                 {'land_size':1.5,'unit':'HECTARE','land_ownership_type':'OWNER'}),
                ('Crop','00000000-0000-4000-8000-000000000003','00000000-0000-4000-8000-000000000002',
                 {'commodity':'CROP_MAIZE'})):
                table = getattr(models,'G2PRegister'+suffix).__table__
                values = {k:v for k,v in farmer.items() if k in table.c}
                values.update(internal_record_id=key,link_internal_record_id=parent,**extra)
                connection.execute(table.insert().values(**values))
        print(json.dumps({'native_ddl':'PASS','tables':len(BaseORMModel.metadata.tables)}))
    else:
        with engine.connect() as connection:
            sections = connection.execute(text('SELECT section_id, section_ui_schema FROM g2p_register_sections ORDER BY section_id')).all()
            # Full section trees, bindings and labels must replay identically.
            result = {'sections': [list(row) for row in sections]}
            for name in ('g2p_intake_form_ui_tab_sections','g2p_register_ui_tab_sections','registry_languages'):
                rows = connection.execute(text(f'SELECT * FROM {name}')).mappings().all()
                result[name] = sorted([dict(row) for row in rows],key=lambda row:json.dumps(row,sort_keys=True,default=str))
            for prefix in ('g2p_register_','g2p_register_history_','g2p_intake_form_'):
                assert connection.execute(text(f'SELECT income_sources FROM {prefix}farmers')).scalar_one() == ['SOI_CROP_PRODUCTION']
            expected = (['MACH_TRACTOR'],['MACH_COMBINE','MACH_TRACTOR'],[])
            for prefix, values in zip(('g2p_register_','g2p_register_history_','g2p_intake_form_'),expected):
                assert connection.execute(text(f'SELECT machinery_types FROM {prefix}farm_inputs')).scalar_one() == values
                assert connection.execute(text(f'SELECT machinery_type FROM {prefix}farm_inputs')).scalar_one() == 'MACH_TRACTOR'
            def widgets(node):
                if isinstance(node, dict):
                    if 'widget' in node:
                        yield node
                    for value in node.values():
                        yield from widgets(value)
                elif isinstance(node, list):
                    for value in node:
                        yield from widgets(value)
            bound = set(connection.execute(text('SELECT section_id FROM g2p_intake_form_ui_tab_sections UNION SELECT section_id FROM g2p_register_ui_tab_sections')).scalars())
            fin_sections = 0
            for section_id, schema in sections:
                if section_id not in bound:
                    continue
                actual = list(widgets(schema))
                fin = [w for w in actual if isinstance(w.get('widget-data-path'), str) and w['widget-data-path'].endswith('.foundational_id')]
                if not fin:
                    continue
                fin_sections += 1
                assert len(fin) == 1, (section_id, 'duplicate FIN inputs', fin)
                assert fin[0].get('widget') == 'display' and fin[0].get('widget-readonly') is True
                assert fin[0].get('widget-required') is False
                assert sum(w.get('widget') == 'oan-identity-verification' for w in actual) == 1, section_id
            assert fin_sections, 'No bound Farmer FIN display was checked'
            section_map = dict(sections)
            for section_id, fields in {
                'oan_farmer_household_lookup': {'is_household_head'},
                'oan_household_information': {'number_of_male_members', 'number_of_female_members'},
            }.items():
                assert section_id in bound, (section_id, 'household section is not bound')
                found = {w.get('widget-id') or w.get('column-key') for w in widgets(section_map[section_id])}
                assert fields <= found, (section_id, fields-found)
            for section_id, schema in sections:
                if section_id == 'oan_farmer_socio_economic_and_health':
                    raw = json.dumps(schema)
                    assert 'income_sources' in raw and 'multi-select' in raw
                    assert 'contains' in raw
            print(json.dumps(result,sort_keys=True,default=str))
    engine.dispose()


def run():
    suffix = uuid.uuid4().hex[:10]
    network = f'oan-farmer-metadata-{suffix}'
    database = network + '-db'
    owner = 'oan.farmer.metadata.owner=' + suffix
    created_network = created_database = False
    image = os.environ.get('OAN_METADATA_TEST_IMAGE','oan/farmer-deploy-tests:20261025')

    def command(*args, data=None):
        result = subprocess.run(args,input=data,capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace')[-3000:])
        return result.stdout

    def native(mode):
        return command('docker','run','--rm','--memory=768m','--network',network,'--entrypoint','python',
            '-v',f'{ROOT.as_posix()}:/repo:ro','-e','PYTHONPATH=/repo/oan-extension/src:/repo/farmer-extension/src',
            '-e','REGISTRY_EXTENSION_MODULE=openg2p_registry_oan_extension',image,
            '/repo/ci/validation/check_native_metadata.py','--probe',database,mode)

    try:
        command('docker','network','create','--label',owner,network)
        created_network = True
        command('docker','run','--detach','--memory=256m','--name',database,'--network',network,'--label',owner,
            '-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB=metadata_check','postgres:15-alpine')
        created_database = True
        for _ in range(120):
            ready = subprocess.run(['docker','exec',database,'pg_isready','-h','127.0.0.1','-U','postgres'],capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError('Disposable PostgreSQL startup timed out')
        print(native('ddl').decode().splitlines()[-1],flush=True)
        files = []
        for domain in ('farmer','oan'):
            files += sorted((ROOT/f'{domain}-extension/src/openg2p_registry_{domain}_extension/meta_data').rglob('*.sql'))
        snapshots = []
        for attempt in (1,2):
            for path in files:
                try:
                    command('docker','exec','-i',database,'psql','-X','-U','postgres','-d','metadata_check',
                        '-v','ON_ERROR_STOP=1',data=path.read_bytes())
                except RuntimeError as error:
                    raise RuntimeError(f'{path.relative_to(ROOT)}: {error}') from error
            snapshots.append(native('snapshot').decode().splitlines()[-1])
        assert snapshots[0] == snapshots[1], 'Repeated metadata differs'
        reporting = (ROOT/'oan-extension/reporting/reporting_views.sql').read_bytes()
        for attempt in (1,2):
            command('docker','exec','-i',database,'psql','-X','-U','postgres','-d','metadata_check',
                '-v','ON_ERROR_STOP=1',data=reporting)
            if attempt == 1:
                command('docker','exec','-i',database,'psql','-X','-U','postgres','-d','metadata_check',
                    '-v','ON_ERROR_STOP=1',data=b'GRANT SELECT ON fr_rpt_land TO PUBLIC;')
        command('docker','exec','-i',database,'psql','-X','-U','postgres','-d','metadata_check',
            '-v','ON_ERROR_STOP=1',data=b"DO $$ BEGIN IF (SELECT main_crop_count FROM fr_rpt_farmer) <> 1 OR (SELECT total_land_ha FROM fr_rpt_farmer) <> 1.5 OR (SELECT main_crop FROM fr_rpt_farmer_main_crop) <> 'CROP_MAIZE' THEN RAISE EXCEPTION 'Native reporting aggregate mismatch'; END IF; IF NOT has_table_privilege('public','fr_rpt_land','SELECT') THEN RAISE EXCEPTION 'Reader grant lost'; END IF; END $$; REFRESH MATERIALIZED VIEW CONCURRENTLY fr_rpt_land; REFRESH MATERIALIZED VIEW CONCURRENTLY fr_rpt_farmer; SELECT main_crop FROM fr_rpt_farmer_main_crop;")
        print(json.dumps({'registry':'farmer','metadata_passes':2,'sql_files_per_pass':len(files),
            'metadata_identical':True,'reporting_replays':2,'reader_grants_preserved':True,'concurrent_refresh':True,'existing_environment_modified':False}),flush=True)
    finally:
        # Names are random, and cleanup additionally verifies our exact owner label.
        if created_database:
            actual = command('docker','inspect','--format','{{index .Config.Labels "oan.farmer.metadata.owner"}}',database).decode().strip()
            if actual != suffix:
                raise RuntimeError('Disposable database owner mismatch; refusing cleanup')
            command('docker','rm','--force',database)
        if created_network:
            actual = command('docker','network','inspect','--format','{{index .Labels "oan.farmer.metadata.owner"}}',network).decode().strip()
            if actual != suffix:
                raise RuntimeError('Disposable network owner mismatch; refusing cleanup')
            command('docker','network','rm',network)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe',nargs=2,metavar=('HOST','MODE'))
    args = parser.parse_args()
    if args.probe:
        probe(*args.probe)
    else:
        run()
