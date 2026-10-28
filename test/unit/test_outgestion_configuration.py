"""Retain administrator-managed outgestion settings through source reseeding."""
from pathlib import Path
import re,sqlite3
import yaml
ROOT=Path(__file__).resolve().parents[2]

def test_oan_reseed_enables_source_without_resetting_native_topic_checkpoint():
    source=(ROOT/'oan-extension/src/oan_farmer_registry_extension/meta_data/50_outgestion.sql').read_text(encoding='utf-8').replace('"public".','')
    db=sqlite3.connect(':memory:')
    db.create_function('NOW',0,lambda:'2026-10-25T00:00:00')
    for table,columns in re.findall(r'INSERT INTO\s+"([a-z0-9_]+)"\s*\((.*?)\)\s*VALUES',source,re.S|re.I):
        names=re.findall(r'"([a-z0-9_]+)"',columns)
        if table=='outgoing_templates':
            continue
        db.execute('CREATE TABLE '+table+' ('+','.join(n+' TEXT'+(' PRIMARY KEY' if i==0 else '') for i,n in enumerate(names))+')')
    db.execute('CREATE TABLE outgoing_templates(template_id TEXT PRIMARY KEY,data_model_id TEXT,register_id TEXT,template_document_id TEXT,created_at TEXT,updated_at TEXT)')
    db.execute('CREATE TABLE g2p_register_definitions(register_id TEXT PRIMARY KEY,outgest_applicable BOOLEAN)')
    farmer='a1a4d25a-1cd4-4356-abac-985a0b3c6bcd'
    db.execute('INSERT INTO g2p_register_definitions VALUES(?,FALSE)',(farmer,))
    db.execute("INSERT INTO g2p_register_definitions VALUES('unrelated',FALSE)")
    db.executescript(source)
    assert db.execute('SELECT outgest_applicable FROM g2p_register_definitions WHERE register_id=?',(farmer,)).fetchone()==(1,)
    db.execute("UPDATE outgoing_topics SET websub_register_status='REGISTERED',websub_register_number_of_attempts='8'")
    db.executescript(source)
    assert db.execute('SELECT websub_register_status,websub_register_number_of_attempts FROM outgoing_topics').fetchone()==('REGISTERED','8')
    assert db.execute("SELECT outgest_applicable FROM g2p_register_definitions WHERE register_id='unrelated'").fetchone()==(0,)


def test_dev_publishers_use_internal_hub():
    config=yaml.safe_load((ROOT/'helm/environments/dev/registry-outgestion.yaml').read_text())['registry']
    for component in ['staffApi','partnerApi','celeryWorker']:
        assert config[component]['envVars']['REGISTRY_CORE_WEBSUB_BASE_URL']=='http://commons-services-websub.commons.svc.cluster.local'
