"""The adopting renderer may pause producers, never replace persistent objects."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

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
