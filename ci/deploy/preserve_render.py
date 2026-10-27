"""Preservation-checked native Helm upgrade with controlled API-only startup."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import shutil

import yaml

from deployment import documents, index, validate
from oan_compat import render
from preserve import require
from preserve_ops import HELM, command

CONTROLLED = {"farmer-registry-staff-portal-api", "farmer-registry-partner-api",
              "farmer-registry-staff-portal-ui", "farmer-registry-staff-ui-public"}


def manifest_hash(docs):
    return hashlib.sha256(json.dumps(docs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


REPAIR_CHECKPOINTS=("helm-forward-repair.json","helm-forward-repair-staff.json")
EMPTY_BOOLEANS={"REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES",
                "REGISTRY_STAFF_PORTAL_API_VALIDATE_ATTRIBUTE_VALUES"}


def repair_proofs(ops, config):
    from preserve import fingerprint
    proofs=[]
    for offset,name in enumerate(REPAIR_CHECKPOINTS):
        if not (ops.directory/name).exists():
            continue
        require(len(proofs)==offset,"Missing preceding repair evidence")
        proof=ops.load(name)
        require(proof["configFingerprint"]==fingerprint(config)
                and proof["failedRevision"]==config["expectedRevision"]+offset+1
                and proof["targetRevision"]==config["expectedRevision"]+offset+2,
                "Forward repair identity mismatch")
        proofs.append(proof)
    return proofs


def installed_revision(ops, config):
    return config["expectedRevision"]+1+len(repair_proofs(ops,config))


def prepare_helm_attempt(ops, config):
    """Bounded, reviewed repairs of the two observed empty native booleans.

    Never clear a pending release or retry an ambiguous/running Helm command.
    Original attempted manifests and logs remain in the protected directory.
    """
    from preserve import fingerprint
    intent=ops.directory/"helm-upgrade-started"
    status=ops.status()
    proofs=repair_proofs(ops,config)
    if intent.exists() and status["info"]["status"]=="deployed":
        ops.verify_installed(config)
        return None
    target=config["expectedRevision"]+1+len(proofs)
    if intent.exists() and status["info"]["status"]=="failed" and status["version"]==target:
        require(len(proofs)<len(REPAIR_CHECKPOINTS),"Reviewed repair limit reached")
        if not proofs:
            require(not intent.read_bytes(),"Ambiguous Helm attempt requires separate review")
        attempted=documents(ops.directory/"candidate-final.yaml")
        if proofs:
            attempt=json.loads(intent.read_text())
            require(attempt.get("targetRevision")==target
                    and attempt.get("candidateSha256")==manifest_hash(attempted),
                    "Unowned forward repair attempt")
        actual=[d for d in yaml.safe_load_all(command(HELM+["get","manifest","farmer-registry","-n","farmer"])) if isinstance(d,dict)]
        require(manifest_hash(actual)==manifest_hash(attempted),"Failed release is not the owned attempted manifest")
        before=documents(ops.directory/"manifest.yaml")+documents(ops.directory/"hooks.yaml")
        validate(before,validation_inventory(actual,documents(ops.directory/"candidate-analysis.yaml")),
                 config["registry"],config["sourceCommit"][:12],images=config["imageProvenance"])
        archive=ops.directory/("failed-helm-attempt-"+str(target))
        archive.mkdir(mode=0o700,exist_ok=True)
        for name in ("helm-upgrade-started","candidate-final.yaml","helm-upgrade.log"):
            source=ops.directory/name
            require(source.is_file() and not source.is_symlink(),"Missing owned attempt evidence")
            saved=archive/name
            if saved.exists():
                require(saved.read_bytes()==source.read_bytes(),"Failed attempt archive changed")
            else:
                shutil.copyfile(source,saved)
        ops.save(REPAIR_CHECKPOINTS[len(proofs)],{"configFingerprint":fingerprint(config),
                 "failedRevision":status["version"],"targetRevision":status["version"]+1,
                 "failedManifestSha256":manifest_hash(actual)})
        proofs=repair_proofs(ops,config)
    if proofs:
        proof=proofs[-1]
        require(status["version"]==proof["failedRevision"] and status["info"]["status"]=="failed",
                "Forward repair requires the exact failed release")
        actual=[d for d in yaml.safe_load_all(command(HELM+["get","manifest","farmer-registry","-n","farmer"])) if isinstance(d,dict)]
        require(manifest_hash(actual)==proof["failedManifestSha256"],"Failed release changed before repair")
        if intent.exists():
            saved=ops.directory/("failed-helm-attempt-"+str(proof["failedRevision"]))/intent.name
            require(intent.read_bytes()==saved.read_bytes(),"A forward repair has already started; inspect its result")
            intent.unlink()
        return proof["failedRevision"]
    require(not intent.exists() and status["version"]==config["expectedRevision"]
            and status["info"]["status"]=="deployed","Ambiguous Helm attempt requires separate review")
    return config["expectedRevision"]


def validate_repair_delta(previous, candidate):
    """This recovery may only remove the erroneously emitted empty boolean."""
    corrected=copy.deepcopy(previous)
    removed=0
    names={"farmer-registry-"+suffix for suffix in
           ("staff-portal-api","partner-api","celery-worker","celery-beat-producer")}
    for doc in corrected:
        if doc.get("kind")=="Deployment" and doc["metadata"]["name"] in names:
            pod=doc["spec"]["template"]["spec"]
            for container in pod.get("containers",[])+pod.get("initContainers",[]):
                env=container.get("env",[])
                def empty_validation(entry):
                    return (entry["name"] in EMPTY_BOOLEANS
                            and entry.get("value") in (None,"") and entry.get("valueFrom") is None)
                removed+=sum(empty_validation(entry) for entry in env)
                container["env"]=[e for e in env if not empty_validation(e)]
    require(removed>0 and index(corrected)==index(candidate),"Unreviewed forward repair manifest change")


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


def preparatory_seed_template(template):
    """DDL already ran; the manual seed must not wait for paused applications."""
    result=copy.deepcopy(template)
    initializers=result.get("initContainers",[])
    names=[container["name"] for container in initializers]
    require(len(names)==len(set(names)) and set(names)=={"wait-for-db","wait-for-apps"},
            "Review changed native seed initialization before adoption")
    # This is the separately tracked preparatory Kubernetes Job. The published
    # chart and native seed entrypoint remain unmodified. LOAD_SAMPLE_DATA=false
    # guarantees the seed does not submit/approve intakes through the APIs.
    result["initContainers"]=[container for container in initializers if container["name"]=="wait-for-db"]
    return result


def validation_inventory(persistent, native_plans):
    """Validate both retained Helm objects and separately executed native Jobs.

    This is a configuration inventory only. These planned Job documents are
    never passed to Helm/apply; real completion uses UID-checked Job receipts.
    """
    require(not any(d.get("kind")=="Job" for d in persistent),"Helm must not execute duplicate native Jobs")
    names={"farmer-registry-db-seed","farmer-registry-sanity"}
    selected=[d for d in native_plans if d.get("kind")=="Job" and d.get("metadata",{}).get("name") in names]
    require(len(selected)==2 and {d["metadata"]["name"] for d in selected}==names,
            "Exact native seed and smoke image plans required")
    return copy.deepcopy(persistent)+copy.deepcopy(selected)


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
    previous_revision=prepare_helm_attempt(ops,config)
    if previous_revision is None:
        return
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
    if (ops.directory/"helm-forward-repair.json").exists():
        validate_repair_delta(documents(ops.directory/("failed-helm-attempt-"+str(previous_revision))/"candidate-final.yaml"),after)
    validate(before,validation_inventory(after,documents(ops.directory/"candidate-analysis.yaml")),
             config["registry"],config["sourceCommit"][:12],images=config["imageProvenance"])
    require(not any(d["kind"]=="Job" for d in after), "Jobs must use tracked native invocations")
    require(ops.status()["version"]==previous_revision,"Helm release changed during final dry run")
    # No --atomic: old application images must never roll back across migration.
    # Record intent before invoking Helm; interrupted results require read-back.
    with intent.open("x") as stream:
        json.dump({"fromRevision":previous_revision,"targetRevision":previous_revision+1,
                   "candidateSha256":manifest_hash(after)},stream)
    command(HELM+["upgrade",*args,"--wait=false","--timeout","10m"],timeout=650,log=ops.directory/"helm-upgrade.log")
    ops.verify_installed(config)


def acceptance(ops, config):
    docs=documents(ops.directory/"candidate-analysis.yaml")
    sanity=[d for d in docs if d["kind"]=="Job" and d["metadata"]["name"]=="farmer-registry-sanity"]
    require(len(sanity)==1,"One native smoke suite required")
    template=sanity[0]["spec"]["template"]["spec"]
    flags={e["name"]:e.get("value") for e in template["containers"][0].get("env",[])}
    require(flags.get("SANITY_RUN_E2E")=="false" and flags.get("SANITY_FAIL_ON_ERROR")=="true",
            "Only read-only native smoke is permitted")
    # Source/render checks are not a substitute for an actual HTTP response.
    # The published API pod can reach its same-origin UI and both internal APIs.
    code = """import json,urllib.request
urls=['http://farmer-registry-staff-portal-api/ping','http://farmer-registry-partner-api/ping','http://farmer-registry-staff-portal-ui/']
result=[]
for url in urls:
 with urllib.request.urlopen(url,timeout=20) as response:
  assert response.status==200
  result.append({'service':url.split('/')[2],'status':response.status})
with urllib.request.urlopen('http://farmer-registry-partner-api/openapi.json',timeout=20) as response:
 assert response.status==200
 paths=json.load(response).get('paths',{})
 methods={path:sorted(paths.get(path,{})) for path in ('/dci/sync/search','/dci/async/search')}
print(json.dumps({'readiness':result,'dciMethods':methods}))
"""
    result=ops.kubectl(["exec","-n","farmer","deploy/farmer-registry-staff-portal-api","-c","staff-portal-api",
                        "--","python3","-c",code],timeout=80)
    checked=json.loads(result)
    require(set(checked["dciMethods"])=={"/dci/sync/search","/dci/async/search"}
            and all("post" in methods for methods in checked["dciMethods"].values()),
            "Current native DCI search contract missing")
    ops.save("http-readiness.json",checked["readiness"])
    ops.save("native-dci-contract.json",{"verification":"current-native-routes-passed",
             "methods":checked["dciMethods"],
             "supersededSmoke":"test_openapi_has_dci_search expects obsolete /dci/registry prefix"})
    # Published rc.557's generic smoke still asserts the pre-current /dci/registry
    # prefix. Its own current controller/functional tests use /dci/sync/search.
    # Public pytest args select remaining native smoke unchanged; the exact
    # replacement route assertion above must pass before any selection occurs.
    template=copy.deepcopy(template)
    require(not template["containers"][0].get("args"),"Unexpected native smoke arguments")
    template["containers"][0]["args"]=["-k","not test_openapi_has_dci_search"]
    ops.native_job("sanity-tests",template)


def converge_empty_booleans(ops):
    """Prune only stale empty entries absent from the approved Helm manifest.

    Helm's strategic merge can retain a name-only env entry when its previous
    manifest contained valueFrom:null. UID/RV tests make this a bounded native
    reconciliation, not a configuration override or whole-workload replacement.
    """
    desired=index(documents(ops.directory/"installed.yaml"))
    snapshot=ops.load("pause-snapshot.json")
    for suffix in ("celery-worker","celery-beat-producer","partner-api","staff-portal-api"):
        name="farmer-registry-"+suffix
        target=desired[("Deployment",name)]
        current=ops.get(["get","deployment",name,"-n","farmer","-o","json"])
        require(current["metadata"]["uid"]==snapshot["deployment/"+name]["uid"],"Convergence workload replaced")
        annotations=current["metadata"].get("annotations",{})
        require(annotations.get("meta.helm.sh/release-name")=="farmer-registry"
                and annotations.get("meta.helm.sh/release-namespace")=="farmer","Convergence ownership mismatch")
        patches=[{"op":"test","path":"/metadata/uid","value":current["metadata"]["uid"]},
                 {"op":"test","path":"/metadata/resourceVersion","value":current["metadata"]["resourceVersion"]}]
        for group in ("containers","initContainers"):
            wanted={c["name"]:c for c in target["spec"]["template"]["spec"].get(group,[])}
            for i,container in enumerate(current["spec"]["template"]["spec"].get(group,[])):
                require(container["name"] in wanted,"Unreviewed convergence container")
                wanted_names={e["name"] for e in wanted[container["name"]].get("env",[])}
                for j in reversed(range(len(container.get("env",[])))):
                    entry=container["env"][j]
                    if entry["name"] in EMPTY_BOOLEANS and entry["name"] not in wanted_names:
                        require(entry=={"name":entry["name"]},"Configured boolean must not be removed")
                        path="/spec/template/spec/"+group+"/"+str(i)+"/env/"+str(j)
                        patches.extend([{"op":"test","path":path,"value":entry},{"op":"remove","path":path}])
        if len(patches)>2:
            # Read-back after every patch; a crash retries only entries remaining.
            ops.kubectl(["patch","deployment",name,"-n","farmer","--type=json","-p",json.dumps(patches)])
            after=ops.get(["get","deployment",name,"-n","farmer","-o","json"])
            require(after["metadata"]["uid"]==current["metadata"]["uid"],"Convergence workload replaced")
            for group in ("containers","initContainers"):
                wanted={c["name"]:{e["name"] for e in c.get("env",[])}
                        for c in target["spec"]["template"]["spec"].get(group,[])}
                for container in after["spec"]["template"]["spec"].get(group,[]):
                    require(not any(e["name"] in EMPTY_BOOLEANS
                            and e["name"] not in wanted[container["name"]] for e in container.get("env",[])),
                            "Empty boolean convergence did not apply")
            ops.save("empty-boolean-convergence-"+suffix+".json",
                     {"uid":current["metadata"]["uid"],"removed":(len(patches)-2)//2})


if __name__ == "__main__":
    try:
        context=json.loads(Path(sys.argv[1]).read_text())
        source=[d for d in yaml.safe_load_all(sys.stdin) if isinstance(d,dict)]
        sys.stdout.write(yaml.safe_dump_all(controlled_render(source,context["values"],context["snapshot"]),sort_keys=False))
    except Exception:
        sys.exit("FAIL: preserving renderer rejected private input")
