"""The adopting renderer may pause producers, never replace persistent objects."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest
from tests.unit.test_jenkins_deployment import release, deployment as delivery_guard, ECR, TAG

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"ci/deploy"))
spec=importlib.util.spec_from_file_location("preserving_render",ROOT/"ci/deploy/preserve_render.py")
render=importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


def deployment(name):
    return {"apiVersion":"apps/v1","kind":"Deployment","metadata":{"name":name,"namespace":"farmer"},
            "spec":{"replicas":1,"selector":{"matchLabels":{"app":name}},
                    "template":{"spec":{"containers":[{"name":"app","image":"example.invalid/retained@sha256:"+"a"*64,
                                                    "env":[{"name":"PRESERVED","valueFrom":{"secretKeyRef":{"name":"existing","key":"value"}}}]}]}}}}


def test_retains_configuration_and_ownership_while_holding_producers():
    api=deployment("farmer-registry-staff-portal-api")
    worker=deployment("farmer-registry-celery-worker")
    snapshot={"deployment/"+d["metadata"]["name"]:{"uid":"original","replicas":2} for d in (api,worker)}
    service={"apiVersion":"v1","kind":"Service","metadata":{"name":"existing"},"spec":{"selector":{"app":"existing"}}}
    secret={"apiVersion":"v1","kind":"Secret","metadata":{"name":"existing"},"data":{"key":"fixture"}}
    job={"apiVersion":"batch/v1","kind":"Job","metadata":{"name":"native-initializer"},"spec":{}}
    source=[api,worker,service,secret,job]
    before=copy.deepcopy(source)
    actual=render.controlled_render(source,{},snapshot)
    assert source==before
    assert [d["kind"] for d in actual]==["Deployment","Deployment","Service","Secret"]
    assert actual[0]["spec"]["replicas"]==2 and actual[1]["spec"]["replicas"]==0
    for index in (0,1):
        expected=copy.deepcopy(source[index])
        expected["spec"]["replicas"]=actual[index]["spec"]["replicas"]
        assert actual[index]==expected
    assert actual[2:]==[service,secret]


def test_rejects_new_unreviewed_workload():
    with pytest.raises(ValueError,match="Unreviewed persistent workload"):
        render.controlled_render([deployment("another")],{}, {})


def test_schedules_stay_suspended_until_verified_resume():
    cron={"apiVersion":"batch/v1","kind":"CronJob","metadata":{"name":"retained"},
          "spec":{"schedule":"0 * * * *","suspend":False,"jobTemplate":{"spec":{"template":{"spec":{"containers":[]}}}}}}
    result=render.controlled_render([cron],{}, {})
    expected=copy.deepcopy(cron);expected["spec"]["suspend"]=True
    assert result==[expected]


def test_runtime_source_matches_the_frozen_published_candidate():
    import preserve_entry
    candidate=json.loads((ROOT/"ci/deploy/adoption-candidate.json").read_text())
    assert preserve_entry.runtime_hash(ROOT)==candidate["runtimeHash"]
    assert candidate["sourceCommit"]=="afdbf75a73227ef0e3a0dfe6824918aee04b70a1"
    assert candidate["chartVersion"]=="1.0.0-dev.16"
    pin=json.loads((ROOT/"ci/deploy/adoption-chart.json").read_text())
    legacy=json.loads((ROOT/"ci/deploy/oan-chart.json").read_text())
    assert pin["sha256"]==candidate["chartSha256"] and pin["preservingAdoption"] is True
    assert pin["promotionReady"] is False and legacy["version"]=="1.0.0-dev.14"


@pytest.mark.parametrize("entry",[
    {"name":"REGISTRY_STAFF_PORTAL_API_AUTH_REDIS_URL","value":"redis://existing.invalid:6379/0"},
    {"name":"REGISTRY_STAFF_PORTAL_API_AUTH_REDIS_URL","valueFrom":{"secretKeyRef":{"name":"existing-redis","key":"url"}}},
])
def test_native_registrant_auth_reuses_existing_redis_literal_or_secret(entry):
    api=deployment("farmer-registry-staff-portal-api")
    api["spec"]["template"]["spec"]["containers"][0]["env"]=[entry]
    values={"registry":{"staffApi":{}}}
    result=render.native_authentication_settings(values,[api])
    field="envVarsFrom" if "valueFrom" in entry else "envVars"
    assert result["registry"]["staffApi"][field]["REGISTRY_CORE_REGISTRANT_AUTH_REDIS_URL"]==entry.get("valueFrom",entry.get("value"))
    assert "localhost" not in str(result)
    assert api["spec"]["template"]["spec"]["containers"][0]["env"]==[entry]


def test_existing_native_redis_is_never_redirected_and_missing_staff_reference_blocks():
    api=deployment("farmer-registry-staff-portal-api")
    entry={"name":"REGISTRY_CORE_REGISTRANT_AUTH_REDIS_URL","value":"redis://already-configured.invalid/2"}
    api["spec"]["template"]["spec"]["containers"][0]["env"]=[entry]
    values={"registry":{"staffApi":{"envVars":{entry["name"]:entry["value"]}}}}
    assert render.native_authentication_settings(copy.deepcopy(values),[api])==values
    api["spec"]["template"]["spec"]["containers"][0]["env"]=[]
    with pytest.raises(ValueError,match="Existing staff auth Redis reference"):
        render.native_authentication_settings(values,[api])


def test_preparatory_seed_keeps_db_wait_and_native_container_but_not_paused_api_wait():
    database={"name":"wait-for-db","image":"native/postgres-checker","command":["pg_isready"]}
    application={"name":"wait-for-apps","image":"busybox:1.36","command":["sh","-c"],"args":["wait for native apps"]}
    template={"initContainers":[database,application],"containers":[{"name":"db-seed","image":"reviewed/native-seed",
              "env":[{"name":"LOAD_SAMPLE_DATA","value":"false"}]}],"volumes":[{"name":"retained","emptyDir":{}}]}
    before=copy.deepcopy(template)
    result=render.preparatory_seed_template(template)
    assert template==before
    expected=copy.deepcopy(before);expected["initContainers"]=[database]
    assert result==expected


@pytest.mark.parametrize("names",[[],["wait-for-db"],["wait-for-db","wait-for-apps","unreviewed"],["wait-for-db","wait-for-db","wait-for-apps"]])
def test_changed_initializer_contract_requires_review(names):
    with pytest.raises(ValueError,match="Review changed native seed initialization"):
        render.preparatory_seed_template({"initContainers":[{"name":name} for name in names]})


def test_strict_guard_still_checks_native_job_images_without_reapplying_them(release):
    before,after=release
    retained=[d for d in after if d["kind"]!="Job"]
    with pytest.raises(ValueError,match="Missing required image workload"):
        delivery_guard.validate(before,retained,ECR,TAG)
    inventory=render.validation_inventory(retained,after)
    delivery_guard.validate(before,inventory,ECR,TAG)
    assert not any(d["kind"]=="Job" for d in retained)
    modified=copy.deepcopy(after)
    next(d for d in modified if d["kind"]=="Job" and d["metadata"]["name"]=="farmer-registry-db-seed")["spec"]["template"]["spec"]["containers"][0]["image"]="foreign/seed:unreviewed"
    with pytest.raises(ValueError,match="Wrong commit image"):
        delivery_guard.validate(before,render.validation_inventory(retained,modified),ECR,TAG)


def test_native_job_plans_cannot_be_missing_duplicated_or_applied_twice():
    seed={"kind":"Job","metadata":{"name":"farmer-registry-db-seed"}}
    smoke={"kind":"Job","metadata":{"name":"farmer-registry-sanity"}}
    for plans in ([],[seed],[seed,seed,smoke]):
        with pytest.raises(ValueError,match="Exact native seed and smoke"):
            render.validation_inventory([],plans)
    with pytest.raises(ValueError,match="duplicate native Jobs"):
        render.validation_inventory([seed],[seed,smoke])


@pytest.mark.parametrize("component,suffix",[
    ("staffApi","staff-portal-api"),("partnerApi","partner-api"),
    ("celeryWorker","celery-worker"),("celeryBeat","celery-beat-producer")])
def test_explicitly_absent_native_boolean_is_not_emitted_as_empty_string(component,suffix):
    name="REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES"
    doc=deployment("farmer-registry-"+suffix)
    env=doc["spec"]["template"]["spec"]["containers"][0]["env"]
    env.extend([{"name":name},{"name":"UNRELATED_EMPTY","value":""}])
    values={"registry":{component:{"envVars":{name:None},"envVarsFrom":{name:None}}}}
    snapshot={"deployment/"+doc["metadata"]["name"]:{"uid":"original","replicas":1}}
    result=render.controlled_render([doc],values,snapshot)[0]
    actual=result["spec"]["template"]["spec"]["containers"][0]["env"]
    assert not any(e["name"]==name for e in actual)
    assert {"name":"UNRELATED_EMPTY","value":""} in actual
    assert any(e["name"]==name for e in env)  # Input is preserved.


@pytest.mark.parametrize("entry",[
    {"name":"REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES","value":"true"},
    {"name":"REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES","value":"false"},
    {"name":"REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES","valueFrom":{"secretKeyRef":{"name":"existing","key":"validation"}}},
])
def test_existing_native_boolean_configuration_is_preserved(entry):
    doc=deployment("farmer-registry-staff-portal-api")
    doc["spec"]["template"]["spec"]["containers"][0]["env"].append(entry)
    field="envVarsFrom" if "valueFrom" in entry else "envVars"
    values={"registry":{"staffApi":{field:{entry["name"]:entry.get("valueFrom",entry.get("value"))}}}}
    snapshot={"deployment/"+doc["metadata"]["name"]:{"uid":"original","replicas":1}}
    assert render.controlled_render([doc],values,snapshot)==[doc]


@pytest.mark.parametrize("empty",[
    {"name":"REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES"},
    {"name":"REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES","valueFrom":None},
    {"name":"REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES","value":None},
])
def test_forward_repair_permits_only_empty_validation_omission(empty):
    before=[deployment("farmer-registry-staff-portal-api")]
    before[0]["spec"]["template"]["spec"]["containers"][0]["env"].append(empty)
    before[0]["spec"]["template"]["spec"]["initContainers"]=[{"name":"database-checker","env":[empty]}]
    after=copy.deepcopy(before)
    after[0]["spec"]["template"]["spec"]["containers"][0]["env"].pop()
    after[0]["spec"]["template"]["spec"]["initContainers"][0]["env"]=[]
    render.validate_repair_delta(before,after)
    changed=copy.deepcopy(after)
    changed[0]["spec"]["template"]["spec"]["containers"][0]["image"]="other/image:latest"
    with pytest.raises(ValueError,match="Unreviewed forward repair"):
        render.validate_repair_delta(before,changed)
    configured=copy.deepcopy(before)
    configured[0]["spec"]["template"]["spec"]["containers"][0]["env"][-1]["value"]="true"
    with pytest.raises(ValueError,match="Unreviewed forward repair"):
        render.validate_repair_delta(configured,after)
    with pytest.raises(ValueError,match="Unreviewed forward repair"):
        render.validate_repair_delta(after,after)


def test_failed_owned_helm_attempt_is_archived_before_one_forward_repair(tmp_path,monkeypatch,release):
    import yaml
    from types import SimpleNamespace
    from tests.unit.test_preserving_adoption import configuration
    config={**configuration(),"registry":ECR,"sourceCommit":TAG+"a"*(40-len(TAG)),"imageProvenance":None}
    before,after=release
    retained=[d for d in after if d["kind"]!="Job"]
    for name,docs in [("manifest.yaml",before),("hooks.yaml",[]),("candidate-final.yaml",retained),("candidate-analysis.yaml",after)]:
        (tmp_path/name).write_text(yaml.safe_dump_all(docs))
    (tmp_path/"helm-upgrade-started").touch()
    (tmp_path/"helm-upgrade.log").write_text("retained private readiness failure")
    ops=SimpleNamespace(directory=tmp_path,status=lambda:{"version":63,"info":{"status":"failed"}},
        load=lambda name:json.loads((tmp_path/name).read_text()),
        save=lambda name,value:(tmp_path/name).write_text(json.dumps(value)))
    monkeypatch.setattr(render,"command",lambda args:yaml.safe_dump_all(retained).encode())
    assert render.prepare_helm_attempt(ops,config)==63
    assert not (tmp_path/"helm-upgrade-started").exists()
    assert (tmp_path/"failed-helm-attempt-63"/"candidate-final.yaml").is_file()
    assert render.installed_revision(ops,config)==64
    assert render.prepare_helm_attempt(ops,config)==63  # Interrupted before retry is safe.
    (tmp_path/"helm-upgrade-started").write_text('{"targetRevision":64}')
    with pytest.raises(ValueError,match="already started"):
        render.prepare_helm_attempt(ops,config)
    ops.status=lambda:{"version":64,"info":{"status":"failed"}}
    with pytest.raises(ValueError,match="Unowned forward repair"):
        render.prepare_helm_attempt(ops,config)
    (tmp_path/"helm-upgrade-started").write_text(json.dumps({
        "targetRevision":64,"candidateSha256":render.manifest_hash(retained)}))
    assert render.prepare_helm_attempt(ops,config)==64
    assert render.installed_revision(ops,config)==65
    assert (tmp_path/"failed-helm-attempt-64"/"helm-upgrade-started").is_file()
    (tmp_path/"helm-upgrade-started").write_text(json.dumps({
        "targetRevision":65,"candidateSha256":render.manifest_hash(retained)}))
    ops.status=lambda:{"version":65,"info":{"status":"failed"}}
    with pytest.raises(ValueError,match="repair limit"):
        render.prepare_helm_attempt(ops,config)


@pytest.mark.parametrize("state,revision,intent",[
    ("pending-upgrade",63,""),("failed",64,""),("failed",63,'{"targetRevision":63}')])
def test_pending_unowned_or_new_attempts_are_not_blindly_retried(tmp_path,state,revision,intent):
    from types import SimpleNamespace
    (tmp_path/"helm-upgrade-started").write_text(intent)
    ops=SimpleNamespace(directory=tmp_path,status=lambda:{"version":revision,"info":{"status":state}})
    with pytest.raises(ValueError,match="Ambiguous Helm attempt"):
        render.prepare_helm_attempt(ops,{"expectedRevision":62})


def test_acceptance_restarts_only_original_controlled_workloads(monkeypatch):
    from types import SimpleNamespace
    from preserve_ops import Operations
    originals=[]
    for name in ["staff-portal-api","staff-portal-ui","partner-api","celery-worker"]:
        row=deployment("farmer-registry-"+name)
        row["metadata"]["uid"]="retained-"+name
        originals.append(row)
    calls=[]
    ops=SimpleNamespace(load=lambda name:originals,
        get=lambda args:next(row for row in originals if row["metadata"]["name"]==args[2]),
        kubectl=lambda args,**kwargs:calls.append(args),
        verify_preservation=lambda config:calls.append(["preservation"]))
    monkeypatch.setattr(render,"acceptance",lambda ops,config:None)
    # Operations imports the canonical module, which can have a separate import
    # identity from this test's explicitly loaded renderer.
    import preserve_render
    monkeypatch.setattr(preserve_render,"acceptance",lambda ops,config:None)
    monkeypatch.setattr(preserve_render,"converge_empty_booleans",lambda ops:None)
    Operations.accept(ops,{})
    scales=[args for args in calls if args[0]=="scale"]
    assert len(scales)==3 and all("celery" not in str(args) for args in scales)
    assert ["preservation"] in calls
    ops.get=lambda args:{"metadata":{"uid":"replacement"}}
    with pytest.raises(ValueError,match="Controlled workload replaced"):
        Operations.accept(ops,{})


def test_staff_specific_validation_alias_uses_native_default_in_main_and_init():
    name="REGISTRY_STAFF_PORTAL_API_VALIDATE_ATTRIBUTE_VALUES"
    doc=deployment("farmer-registry-staff-portal-api")
    pod=doc["spec"]["template"]["spec"]
    pod["containers"][0]["env"].append({"name":name,"valueFrom":None})
    pod["initContainers"]=[{"name":"db-checker","env":[{"name":name,"valueFrom":None}]}]
    values={"registry":{"staffApi":{"envVars":{name:None},"envVarsFrom":{name:None}}}}
    snapshot={"deployment/"+doc["metadata"]["name"]:{"uid":"original","replicas":1}}
    after=render.controlled_render([doc],values,snapshot)
    assert all(not any(e["name"]==name for e in c.get("env",[]))
               for group in ("containers","initContainers") for c in after[0]["spec"]["template"]["spec"].get(group,[]))
    render.validate_repair_delta([doc],after)


@pytest.mark.parametrize("configured",[False,True])
def test_native_convergence_only_removes_stale_empty_entries_and_is_idempotent(tmp_path,configured):
    import yaml
    from types import SimpleNamespace
    desired=[];current={};snapshot={};saved=[];calls=[]
    for suffix in ("celery-worker","celery-beat-producer","partner-api","staff-portal-api"):
        name="farmer-registry-"+suffix
        d=deployment(name)
        desired.append(copy.deepcopy(d))
        d["metadata"].update(uid=name,resourceVersion="123",annotations={
            "meta.helm.sh/release-name":"farmer-registry","meta.helm.sh/release-namespace":"farmer"})
        flag={"name":"REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES"}
        if configured:flag["value"]="true"
        d["spec"]["template"]["spec"]["containers"][0]["env"].append(flag)
        current[name]=d;snapshot["deployment/"+name]={"uid":name}
    (tmp_path/"installed.yaml").write_text(yaml.safe_dump_all(desired))
    def patch(args):
        patches=json.loads(args[-1]);calls.append(patches)
        assert patches[0]["op"]==patches[1]["op"]=="test"
        assert patches[2]["value"]=={"name":"REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES"}
        current[args[2]]["spec"]["template"]["spec"]["containers"][0]["env"].pop()
    ops=SimpleNamespace(directory=tmp_path,load=lambda name:snapshot,
        get=lambda args:copy.deepcopy(current[args[2]]),kubectl=patch,
        save=lambda name,value:saved.append(value))
    if configured:
        with pytest.raises(ValueError,match="Configured boolean"):
            render.converge_empty_booleans(ops)
        assert not calls
    else:
        render.converge_empty_booleans(ops)
        assert len(calls)==4 and len(saved)==4
        render.converge_empty_booleans(ops)
        assert len(calls)==4
