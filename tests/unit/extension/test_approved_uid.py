import ast
from datetime import date
from pathlib import Path
import re
import pytest

ROOT=Path(__file__).resolve().parents[3]
SERVICES=ROOT/'farmer-extension/src/openg2p_registry_farmer_extension/register_domain/services'
namespace={'date':date,'re':re}
source=ast.parse((SERVICES/'approved_uid.py').read_text())
exec(compile(ast.Module(body=[n for n in source.body if isinstance(n,ast.FunctionDef)],type_ignores=[]),'approved_uid.py','exec'),namespace)
choose=namespace['choose_projection'];fan=namespace['fan_value']
A='9988102320260001';B='9988102320260002'
def uid(value=A,**overrides):
    return {'id_type':'UID','value':value,'record_status':'ACTIVE','status':'VALID','expiry_date':None,'last_approved_at':'2026-10-22','last_approved_by':'approver',**overrides}

@pytest.mark.parametrize('value',[A,'FAN-'+A,' '.join(A[i:i+4] for i in range(0,16,4))])
def test_normalizes_only_complete_fans(value):assert fan(value)==A
@pytest.mark.parametrize('value',[None,'','1'*12,'x'*16,'9'*17,'?'*16])
def test_does_not_confuse_fin_or_malformed_values_with_fan(value):assert fan(value) is None

def test_approved_unique_fan_and_duplicate_same_value_are_safe():
    assert choose(None,[uid()])[0]==A
    assert choose(None,[uid(),uid()])[0]==A

@pytest.mark.parametrize('overrides',[{'record_status':'INACTIVE'},{'status':'INVALID'},{'last_approved_at':None},{'last_approved_by':None},{'expiry_date':date(2000,1,1)},{'id_type':'RID'}])
def test_unapproved_invalid_expired_or_other_ids_cannot_supply_identity(overrides):
    assert choose(None,[uid(**overrides)])[0] is None

def test_today_expiry_is_still_current():assert choose(None,[uid(expiry_date=date.today())])[0]==A

def test_approved_replacement_and_revocation_update_only_uid_owned_projection():
    assert choose(A,[uid(B)],[A])[0]==B
    assert choose(A,[uid(status='INVALID')],[A])[0] is None
    assert choose(A,[],[A])[0] is None

def test_independent_identity_is_preserved():
    assert choose('123456789012',[uid()])[0]=='123456789012'
    assert choose(B,[uid()])[0]==B

def test_conflicting_uids_do_not_arbitrarily_choose_an_identity():
    assert choose(None,[uid(A),uid(B)])[0] is None
    assert choose(A,[uid(A),uid(B)])[0] is None

def test_native_parent_and_child_hooks_wire_identity_projection():
    for filename in ['g2p_register_domain_service_farmer.py','g2p_register_domain_service_reg_id.py']:
        tree=ast.parse((SERVICES/filename).read_text())
        hooks={n.name:n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name in ['post_approve','post_ingest']}
        assert set(hooks)=={'post_approve','post_ingest'}
        for hook in hooks.values():
            assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='sync_approved_uid' for n in ast.walk(hook))
