"""Retain administrator-managed outgestion settings through source reseeding."""
from pathlib import Path
import re,sqlite3
import yaml
ROOT=Path(__file__).resolve().parents[2]

def test_reseed_preserves_switch_and_new_registers_default_off():
    path=ROOT/'farmer-extension/src/openg2p_registry_farmer_extension/meta_data/register-metadata/g2p_register_definitions.sql'
    source=path.read_text(encoding='utf-8').replace('"public".','')
    columns=re.search(r'INSERT INTO\s+"g2p_register_definitions"\s*\((.*?)\)\s*VALUES',source,re.S|re.I)[1]
    names=re.findall(r'"([a-z_]+)"',columns)
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE g2p_register_definitions ('+','.join(n+' TEXT'+(' PRIMARY KEY' if n=='register_id' else '') for n in names)+')')
    db.executescript(source)
    fid='a1a4d25a-1cd4-4356-abac-985a0b3c6bcd'
    assert db.execute('SELECT outgest_applicable FROM g2p_register_definitions WHERE register_id=?',(fid,)).fetchone()==('FALSE',)
    db.execute("UPDATE g2p_register_definitions SET outgest_applicable='TRUE' WHERE register_id=?",(fid,))
    db.executescript(source)
    assert db.execute('SELECT outgest_applicable FROM g2p_register_definitions WHERE register_id=?',(fid,)).fetchone()==('TRUE',)

def test_dev_publishers_use_internal_hub():
    config=yaml.safe_load((ROOT/'helm/environments/dev/registry-outgestion.yaml').read_text())['registry']
    for component in ['staffApi','partnerApi','celeryWorker']:
        assert config[component]['envVars']['REGISTRY_CORE_WEBSUB_BASE_URL']=='http://commons-services-websub.commons.svc.cluster.local'
