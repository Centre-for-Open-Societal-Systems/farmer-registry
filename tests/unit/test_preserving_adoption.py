"""Ordering, data-preservation and interrupted-operation failure boundaries."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("preserve", ROOT/"ci/deploy/preserve.py")
preserve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preserve)


def configuration():
    source = "a"*40
    return {"mode":"preserving-upgrade","clusterUid":preserve.CLUSTER,"namespace":"farmer",
            "release":"farmer-registry","database":"farmer_registry","sourceCommit":source,
            "chartVersion":"1.0.0-dev.16","chartSha256":"b"*64,"expectedRevision":62,
            "images":{role:"123456789012.dkr.ecr.ap-south-1.amazonaws.com/openg2p/farmer-registry/"
                      +role+":"+source[:12]+"@sha256:"+"c"*64 for role in preserve.ROLES}}


class Store:
    def __init__(self):
        self.version,self.receipt = None,None
        self.history=[]
    def check_cluster(self):
        pass
    def read(self):
        return self.version,copy.deepcopy(self.receipt)
    def cas(self, version, receipt):
        if version != self.version: raise ValueError("CAS conflict")
        self.version=(self.version or 0)+1
        self.receipt=copy.deepcopy(receipt)
        self.history.append(copy.deepcopy(receipt))
        return self.version


class Actions:
    def __init__(self):
        self.events=[]
        self.failure=None
    def event(self,name):
        self.events.append(name)
        if self.failure == name: raise RuntimeError("Injected owned failure")
    def preflight(self,c): self.event("preflight")
    def snapshot(self,c):
        self.event("snapshot")
        return {"deployment/exact":{"uid":"owned","replicas":1}}
    def pause(self,w): self.event("pause")
    def assert_paused(self,w): self.event("assert_paused")
    def backup(self,c):
        self.event("backup")
        return {"restoreVerified":True,"hash":"protected"}
    def verify_backup(self,b):
        self.event("verify_backup")
        assert b["restoreVerified"]
    def native_migrate(self,c): self.event("native_migrate")
    def native_seed(self,c): self.event("native_seed")
    def verify_preservation(self,c): self.event("verify_preservation")
    def expires_at(self): return 9999999999
    def upgrade(self,c,r):
        self.event("upgrade")
        assert r["state"]=="NATIVE_READY" and r["lock"] and r["backupVerified"] and r["originalBusinessPreserved"]
    def verify_installed(self,c): self.event("verify_installed")
    def accept(self,c): self.event("accept")
    def resume(self,w): self.event("resume")


def test_preserving_sequence_and_native_ready_receipt():
    store,actions=Store(),Actions()
    result=preserve.adopt(configuration(),store,actions,initialize=True)
    assert result["state"]=="VERIFIED" and store.receipt["lock"] is None
    ordered=["snapshot","pause","backup","native_migrate","native_seed","verify_preservation","upgrade","accept","resume"]
    positions=[actions.events.index(name) for name in ordered]
    assert positions==sorted(positions)
    assert not any("reset" in name or "drop" in name or "create_database" in name for name in actions.events)
    assert next(r for r in store.history if r["state"]=="NATIVE_READY")["backupVerified"]


@pytest.mark.parametrize("stage",["pause","backup","native_migrate","native_seed","verify_preservation","upgrade","accept","resume"])
def test_failure_keeps_writers_paused_and_never_claims_verified(stage):
    store,actions=Store(),Actions()
    actions.failure=stage
    with pytest.raises(RuntimeError): preserve.adopt(configuration(),store,actions,initialize=True)
    assert store.receipt["state"]!="VERIFIED"
    assert store.receipt["lock"] is None
    assert actions.events[-1]=="pause"
    if stage not in ("resume",):
        assert "resume" not in actions.events


def test_missing_receipt_and_changed_manifest_or_lock_refused():
    config=configuration()
    with pytest.raises(ValueError): preserve.adopt(config,Store(),Actions(),resume=True)
    store,actions=Store(),Actions()
    actions.failure="native_migrate"
    with pytest.raises(RuntimeError): preserve.adopt(config,store,actions,initialize=True)
    actions.failure=None
    with pytest.raises(ValueError): preserve.adopt(config,store,actions)
    with pytest.raises(ValueError): preserve.adopt({**config,"expectedRevision":63},store,actions,resume=True)
    store.receipt["lock"]="d"*32
    with pytest.raises(ValueError): preserve.adopt(config,store,actions,resume=True)


def test_snapshot_failure_does_not_attempt_unknown_workload_mutation():
    store,actions=Store(),Actions()
    actions.failure='snapshot'
    with pytest.raises(RuntimeError): preserve.adopt(configuration(),store,actions,initialize=True)
    assert 'pause' not in actions.events
    assert store.receipt['state']=='PLANNED' and store.receipt['lock'] is None


def test_resume_keeps_verified_backup_and_does_not_replay_completed_native_work():
    store,actions=Store(),Actions()
    actions.failure="accept"
    with pytest.raises(RuntimeError): preserve.adopt(configuration(),store,actions,initialize=True)
    assert store.receipt["state"]=="UPGRADED"
    actions.failure=None
    actions.events=[]
    preserve.adopt(configuration(),store,actions,resume=True)
    assert store.receipt["state"]=="VERIFIED"
    assert not {"backup","native_migrate","native_seed","upgrade"} & set(actions.events)


def test_verified_reentry_only_reads_installed_state():
    store,actions=Store(),Actions()
    preserve.adopt(configuration(),store,actions,initialize=True)
    actions.events=[]
    preserve.adopt(configuration(),store,actions,resume=True)
    assert actions.events==["verify_installed"]


@pytest.mark.parametrize("field,value",[("namespace","far"),("clusterUid","other"),("database","awe"),
    ("mode","reset"),("expectedRevision",True),("expectedRevision",0),("chartVersion","latest"),("sourceCommit","latest")])
def test_wrong_target_or_mutable_release_is_refused_before_actions(field,value):
    actions=Actions()
    with pytest.raises(ValueError): preserve.adopt({**configuration(),field:value},Store(),actions,initialize=True)
    assert not actions.events
