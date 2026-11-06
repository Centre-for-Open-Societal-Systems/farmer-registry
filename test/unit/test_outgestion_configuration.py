"""Retain administrator-managed outgestion settings through source reseeding."""
from pathlib import Path
import re,sqlite3
import yaml
ROOT=Path(__file__).resolve().parents[2]

def test_oan_reseed_enables_source_without_resetting_native_topic_checkpoint():
    source=(ROOT/'farmer-extension/src/openg2p_registry_farmer_extension/meta_data/zz-oan/50_outgestion.sql').read_text(encoding='utf-8').replace('"public".','')
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
    config=yaml.safe_load((ROOT/'helm/environments/dev/farmer-outgestion.yaml').read_text())['registry']
    for component in ['staffApi','partnerApi','celeryWorker']:
        assert config[component]['envVars']['REGISTRY_CORE_WEBSUB_BASE_URL']=='http://commons-services-websub.commons.svc.cluster.local'


def test_seed_switches_the_change_notice_to_its_readable_topic_once():
    source=(ROOT/'farmer-extension/src/openg2p_registry_farmer_extension/meta_data/zz-oan/50_outgestion.sql').read_text(encoding='utf-8').replace('"public".','')
    db=sqlite3.connect(':memory:')
    for table,columns in re.findall(r'INSERT INTO\s+"([a-z0-9_]+)"\s*\((.*?)\)\s*VALUES',source,re.S|re.I):
        if table=='outgoing_templates':
            continue
        names=re.findall(r'"([a-z0-9_]+)"',columns)
        db.execute('CREATE TABLE '+table+' ('+','.join(n+' TEXT'+(' PRIMARY KEY' if i==0 else '') for i,n in enumerate(names))+')')
    db.execute('CREATE TABLE outgoing_templates(template_id TEXT PRIMARY KEY,data_model_id TEXT,register_id TEXT,template_document_id TEXT,created_at TEXT,updated_at TEXT)')
    db.execute('CREATE TABLE g2p_register_definitions(register_id TEXT PRIMARY KEY,outgest_applicable BOOLEAN)')
    # an environment seeded before the switch: the old topic is live and registered with the hub
    db.execute("INSERT INTO outgoing_topics(topic_id,data_model_id,websub_topic,is_active,websub_register_status) VALUES"
               "('farmer_reference_changed_v1_topic','873c2342-cfde-5db4-9f9f-6e491a5001f7','oan.farmer-reference.changed.v1',TRUE,'REGISTERED')")
    db.executescript(source)
    active=db.execute('SELECT topic_id,data_model_id,websub_topic,websub_register_status FROM outgoing_topics WHERE is_active').fetchall()
    assert active==[('farmer_changed_v1_topic','farmer_changed_v1','farmer-registry.farmer.changed.v1','PENDING')]
    assert db.execute("SELECT template_document_id FROM outgoing_templates WHERE data_model_id='farmer_changed_v1'").fetchall()==[('farmer_changed_v1_document',)]
    template=(ROOT/'farmer-extension/src/openg2p_registry_farmer_extension/templates/farmer_changed_v1.j2').read_text(encoding='utf-8')
    assert '"event_type": "farmer-registry.farmer.changed.v1"' in template
    # the hub state the worker writes for the new topic survives a reseed
    db.execute("UPDATE outgoing_topics SET websub_register_status='REGISTERED' WHERE topic_id='farmer_changed_v1_topic'")
    db.executescript(source)
    assert db.execute("SELECT websub_register_status FROM outgoing_topics WHERE topic_id='farmer_changed_v1_topic'").fetchone()==('REGISTERED',)
