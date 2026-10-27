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
