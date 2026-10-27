"""Preservation-checked native Helm upgrade with controlled API-only startup."""
import copy
import json
import os
from pathlib import Path
import sys

import yaml

from deployment import documents, index, validate
from oan_compat import render
from preserve import require
from preserve_ops import HELM, command

CONTROLLED = {"farmer-registry-staff-portal-api", "farmer-registry-partner-api",
              "farmer-registry-staff-portal-ui", "farmer-registry-staff-ui-public"}


def native_authentication_settings(values, before):
    """Core has a separate Redis setting; reuse the installed staff auth store."""
    from deployment import envs
    api=index(before)[("Deployment","farmer-registry-staff-portal-api")]
    variables=list(envs(api,include_init=False).values())
    require(len(variables)==1,"One installed staff API container required")
    native="REGISTRY_CORE_REGISTRANT_AUTH_REDIS_URL"
    if native in variables[0]:
        return values
    existing=variables[0].get("REGISTRY_STAFF_PORTAL_API_AUTH_REDIS_URL")
    require(existing and (existing.get("value") or existing.get("valueFrom")),"Existing staff auth Redis reference required")
    settings=values["registry"]["staffApi"]
    field,other=("envVarsFrom","envVars") if "valueFrom" in existing else ("envVars","envVarsFrom")
    settings.setdefault(field,{})[native]=copy.deepcopy(existing.get("valueFrom",existing.get("value")))
    settings.setdefault(other,{})[native]=None
    return values


def controlled_render(docs, values, snapshot):
    """Retain every persistent object. Native Jobs are executed separately.

    Fresh database/realm/user initialization is intentionally not replayed on
    an existing installation. The native migration, seed, reporting and smoke
    Jobs have explicit receipt-checked invocations in the preserving protocol.
    """
    result = render(docs, values)
    result = [doc for doc in result if doc.get("kind") != "Job"]
    known = {resource.split("/",1)[1]:row for resource,row in snapshot.items()}
    for doc in result:
        if doc.get("kind") in ("Deployment","StatefulSet"):
            name=doc["metadata"]["name"]
            require(name in known, "Unreviewed persistent workload")
            doc["spec"]["replicas"] = known[name]["replicas"] if name in CONTROLLED else 0
        elif doc.get("kind")=="CronJob":
            doc.setdefault("spec",{})["suspend"]=True
    return result


def upgrade(ops, config, receipt):
    from oan_chart import verify
    verify(ops.chart, ops.pin)
    intent=ops.directory/"helm-upgrade-started"
    if intent.exists():
        ops.verify_installed(config)
        return
    require(ops.status()["version"]==config["expectedRevision"], "Helm revision changed before upgrade")
    values=copy.deepcopy(ops.load("prepared-values.json"))
    values["farmerAdoption"]={"mode":"preserving-upgrade","sourceCommit":config["sourceCommit"],
                              "chartSha256":config["chartSha256"]}
    (ops.directory/"upgrade-values.yaml").write_text(yaml.safe_dump(values,sort_keys=False))
    context={"values":values,"snapshot":receipt["workloads"]}
    ops.save("renderer-context.json",context)
    renderer=ops.directory/"post-renderer.sh"
    # All paths are controller-owned UUID folders without shell metacharacters.
    renderer.write_text("#!/bin/sh\nset -eu\nexec python3 "+str(ops.source/"ci/deploy/preserve_render.py")
                        +" "+str(ops.directory/"renderer-context.json")+"\n")
    renderer.chmod(0o700)
    args=["farmer-registry",str(ops.chart),"-n","farmer","-f",str(ops.directory/"upgrade-values.yaml"),
          "--no-hooks","--post-renderer",str(renderer)]
    raw=command(HELM+["template",*args,"--is-upgrade","--dry-run=server"],timeout=180)
    (ops.directory/"candidate-final.yaml").write_bytes(raw)
    before=documents(ops.directory/"manifest.yaml")+documents(ops.directory/"hooks.yaml")
    after=documents(ops.directory/"candidate-final.yaml")
    validate(before,after,config["registry"],config["sourceCommit"][:12],images=config["imageProvenance"])
    require(not any(d["kind"]=="Job" for d in after), "Jobs must use tracked native invocations")
    require(ops.status()["version"]==config["expectedRevision"],"Helm release changed during final dry run")
    # No --atomic: old application images must never roll back across migration.
    # Record intent before invoking Helm; interrupted results require read-back.
    intent.touch(exist_ok=False)
    command(HELM+["upgrade",*args,"--wait","--timeout","10m"],timeout=650,log=ops.directory/"helm-upgrade.log")
    ops.verify_installed(config)


def acceptance(ops, config):
    docs=documents(ops.directory/"candidate-analysis.yaml")
    sanity=[d for d in docs if d["kind"]=="Job" and d["metadata"]["name"]=="farmer-registry-sanity"]
    require(len(sanity)==1,"One native smoke suite required")
    template=sanity[0]["spec"]["template"]["spec"]
    flags={e["name"]:e.get("value") for e in template["containers"][0].get("env",[])}
    require(flags.get("SANITY_RUN_E2E")=="false" and flags.get("SANITY_FAIL_ON_ERROR")=="true",
            "Only read-only native smoke is permitted")
    ops.native_job("sanity-tests",template)
    # Source/render checks are not a substitute for an actual HTTP response.
    # The published API pod can reach its same-origin UI and both internal APIs.
    code = """import json,urllib.request
urls=['http://farmer-registry-staff-portal-api/ping','http://farmer-registry-partner-api/ping','http://farmer-registry-staff-portal-ui/']
result=[]
for url in urls:
 with urllib.request.urlopen(url,timeout=20) as response:
  assert response.status==200
  result.append({'service':url.split('/')[2],'status':response.status})
print(json.dumps(result))
"""
    result=ops.kubectl(["exec","-n","farmer","deploy/farmer-registry-staff-portal-api","-c","staff-portal-api",
                        "--","python3","-c",code],timeout=80)
    ops.save("http-readiness.json",json.loads(result))


if __name__ == "__main__":
    try:
        context=json.loads(Path(sys.argv[1]).read_text())
        source=[d for d in yaml.safe_load_all(sys.stdin) if isinstance(d,dict)]
        sys.stdout.write(yaml.safe_dump_all(controlled_render(source,context["values"],context["snapshot"]),sort_keys=False))
    except Exception:
        sys.exit("FAIL: preserving renderer rejected private input")
