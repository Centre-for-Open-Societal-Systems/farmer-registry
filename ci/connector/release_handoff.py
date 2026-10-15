"""Guarded replica changes using the installed connector charts and Helm values.

Run on the trusted dev host. Private original values/manifests are retained in a
new operator directory. No chart dependencies, migrations or setup Jobs execute.
"""
import argparse
import base64
import copy
import gzip
import json
import os
from pathlib import Path
import subprocess

import yaml

OLD = "farmer-connector"
NEW = "farmer-registry-connector"


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError("Connector Helm operation failed; private output withheld")
    return result.stdout


def documents(raw):
    return [item for item in yaml.safe_load_all(raw) if item]


def replica_guard(before, after, release, replicas):
    def index(items):
        return {(d["kind"], d["metadata"]["name"]): copy.deepcopy(d) for d in items}
    old, new = index(before), index(after)
    if len(old) != len(before) or len(new) != len(after) or set(old) != set(new):
        raise ValueError("Replica handoff must preserve every resource")
    for key, previous in old.items():
        current = new[key]
        if key[0] == "Deployment":
            suffix = key[1].removeprefix(release + "-")
            if suffix not in replicas or current["spec"].get("replicas", 1) != replicas[suffix]:
                raise ValueError("Unexpected connector process or replica count")
            current["spec"]["replicas"] = previous["spec"].get("replicas", 1)
    if old != new:
        raise ValueError("Replica handoff would change unrelated configuration")


def export_chart(release, version, directory):
    secret = json.loads(run(["kubectl", "-n", "farmer", "get", "secret",
                            f"sh.helm.release.v1.{release}.v{version}", "-o", "json"]))
    saved = json.loads(gzip.decompress(base64.b64decode(base64.b64decode(secret["data"]["release"]))))
    chart = saved["chart"]
    directory.mkdir(mode=0o700)
    metadata = chart["metadata"]
    metadata.pop("dependencies", None)
    (directory / "Chart.yaml").write_text(yaml.safe_dump(metadata))
    (directory / "values.yaml").write_text(yaml.safe_dump(chart["values"]))
    for item in chart["templates"]:
        relative = Path(item["name"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid installed template path")
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(item["data"]))
    for item in chart.get("files", []):
        relative = Path(item["name"])
        if relative.is_absolute() or ".." in relative.parts or relative.name in ("Chart.yaml", "values.yaml"):
            raise ValueError("Invalid installed chart file path")
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(item["data"]))
    return saved


def route_guard(before, after, new_route=False):
    old = {(d["kind"], d["metadata"]["name"]): copy.deepcopy(d) for d in before}
    new = {(d["kind"], d["metadata"]["name"]): copy.deepcopy(d) for d in after}
    key = "VirtualService", NEW if new_route else OLD
    if new_route:
        if set(new) - set(old) != {key} or set(old) - set(new):
            raise ValueError("Ingress handoff may only add the replacement route")
        route = new.pop(key)["spec"]
    else:
        if set(old) != set(new): raise ValueError("Routing handoff must preserve every resource")
        route = new[key]["spec"]
    if route["hosts"] != ["connector-farmer-registry-development.oanstaging.com"] or route["gateways"] != ["internal"]:
        raise ValueError("Connector routing environment changed")
    for item in route["http"]:
        if len(item["route"]) != 1: raise ValueError("Unexpected connector route")
        destination = item["route"][0]["destination"]
        if destination["host"] not in (NEW+"-api", NEW+"-ui"):
            raise ValueError("Connector must route only to its replacement services")
        if not new_route:
            destination["host"] = destination["host"].replace(NEW, OLD, 1)
    if old != new: raise ValueError("Routing handoff would change unrelated resources")


def handoff_route(directory, new_route=False):
    release = NEW if new_route else OLD
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    status = json.loads(run(["helm", "status", release, "-n", "farmer", "-o", "json"]))
    before = documents(run(["helm", "get", "manifest", release, "-n", "farmer"]))
    values = yaml.safe_load(run(["helm", "get", "values", release, "-n", "farmer", "-o", "yaml"]))
    chart = directory / "chart"; export_chart(release, status["version"], chart)
    if new_route:
        old_values = yaml.safe_load(run(["helm", "get", "values", OLD, "-n", "farmer", "-o", "yaml"]))
        values["istio"] = old_values["istio"]
        values["global"]["hostname"] = old_values["global"]["hostname"]
    else:
        template = chart / "templates/virtualservice.yaml"
        source = template.read_text()
        for scope in ("$", "."):
            anchor = '{{ include "openg2p-connector.fullname" '+scope+' }}'
            for role in ("api", "ui"):
                source = source.replace('host: '+anchor+'-'+role, 'host: {{ .Values.cossRoutingTarget | default "'+NEW+'" }}-'+role if scope=="." else 'host: {{ $.Values.cossRoutingTarget | default "'+NEW+'" }}-'+role)
        template.write_text(source)
        values["cossRoutingTarget"] = NEW
    path = directory / "values.yaml"; path.write_text(yaml.safe_dump(values))
    options = [release, str(chart), "-n", "farmer", "-f", str(path), "--no-hooks"]
    after = documents(run(["helm", "template", *options, "--is-upgrade", "--dry-run=server"]))
    route_guard(before, after, new_route)
    if json.loads(run(["helm", "status", release, "-n", "farmer", "-o", "json"]))["version"] != status["version"]:
        raise ValueError("Connector changed during route handoff")
    run(["helm", "upgrade", *options, "--atomic", "--wait", "--timeout", "3m"])
    route_guard(before, documents(run(["helm", "get", "manifest", release, "-n", "farmer"])), new_route)
    return {"routeOwner": release, "helmRevision": status["version"]+1, "destination": NEW}


def change_replicas(release, replicas, directory):
    if release not in (OLD, NEW):
        raise ValueError("Unknown connector owner")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    status = json.loads(run(["helm", "status", release, "-n", "farmer", "-o", "json"]))
    if status["info"]["status"] != "deployed":
        raise ValueError("Deployed connector release required")
    before_raw = run(["helm", "get", "manifest", release, "-n", "farmer"])
    before = documents(before_raw)
    (directory / "before.yaml").write_text(before_raw)
    values = yaml.safe_load(run(["helm", "get", "values", release, "-n", "farmer", "-o", "yaml"]))
    (directory / "original-values.yaml").write_text(yaml.safe_dump(values))
    chart = directory / "chart"
    export_chart(release, status["version"], chart)
    # Existing old init dependency resources are retained verbatim; no chart
    # download or setup rerun is involved in stopping scheduling/processing.
    values.setdefault("postgres-init", {})["enabled"] = False
    for role, count in replicas.items():
        values.setdefault(role, {})["replicaCount"] = count
    path = directory / "values.yaml"
    path.write_text(yaml.safe_dump(values))
    base = ["helm", "template", release, str(chart), "-n", "farmer", "-f", str(path), "--is-upgrade", "--dry-run=server", "--no-hooks"]
    candidate = documents(run(base))
    present = {(d["kind"], d["metadata"]["name"]) for d in candidate}
    retained = [d for d in before if (d["kind"], d["metadata"]["name"]) not in present]
    allowed = {("ServiceAccount", "farmer-connector-postgres-init"), ("Job", "farmer-connector-postgres-init-farmer-connector")}
    if any((d["kind"], d["metadata"]["name"]) not in allowed for d in retained):
        raise ValueError("Unreviewed dependency resources")
    if retained:
        (chart / "retained.yaml").write_text(yaml.safe_dump_all(retained))
        (chart / "templates/retained.yaml").write_text('{{ .Files.Get "retained.yaml" }}\n')
    after = documents(run(base))
    replica_guard(before, after, release, replicas)
    current = json.loads(run(["helm", "status", release, "-n", "farmer", "-o", "json"]))
    if current["version"] != status["version"]:
        raise ValueError("Connector changed during handoff")
    run(["helm", "upgrade", release, str(chart), "-n", "farmer", "-f", str(path),
         "--no-hooks", "--atomic", "--wait", "--timeout", "3m"])
    replica_guard(before, documents(run(["helm", "get", "manifest", release, "-n", "farmer"])), release, replicas)
    final = json.loads(run(["helm", "status", release, "-n", "farmer", "-o", "json"]))
    return {"release": release, "helmRevision": final["version"], "replicas": replicas,
            "privateRecoveryDirectory": str(directory), "setupJobsExecuted": False}


def scheduler_guard(before, after):
    old = {(d["kind"], d["metadata"]["name"]): copy.deepcopy(d) for d in before}
    new = {(d["kind"], d["metadata"]["name"]): copy.deepcopy(d) for d in after}
    key = "Deployment", NEW + "-beat"
    if set(new) - set(old) != {key} or set(old) - set(new):
        raise ValueError("Scheduler activation may only add the replacement beat")
    worker = old[("Deployment", NEW + "-worker")]["spec"]["template"]["spec"]
    beat = new.pop(key)["spec"]
    if beat.get("replicas") != 1:
        raise ValueError("One replacement scheduler required")
    current = beat["template"]["spec"]
    expected = copy.deepcopy(worker)
    expected["containers"][0]["name"] = "connector-beat"
    expected["containers"][0]["args"] = ["beat"]
    if current != expected or old != new:
        raise ValueError("Scheduler activation would change unrelated configuration")


def activate_scheduler(directory, checkpoint_evidence):
    if checkpoint_evidence.get("checkpointReconciled") is not True or checkpoint_evidence.get("pipelinesPaused") is not True:
        raise ValueError("Final checkpoint evidence required")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    status = json.loads(run(["helm", "status", NEW, "-n", "farmer", "-o", "json"]))
    before = documents(run(["helm", "get", "manifest", NEW, "-n", "farmer"]))
    values = yaml.safe_load(run(["helm", "get", "values", NEW, "-n", "farmer", "-o", "yaml"]))
    chart = directory / "chart"
    export_chart(NEW, status["version"], chart)
    values["beat"]["enabled"] = True
    values["beat"]["replicaCount"] = 1
    values["cossCutover"] = {"phase": "active", "checkpointBackupHash": checkpoint_evidence["snapshotHash"]}
    path = directory / "values.yaml"; path.write_text(yaml.safe_dump(values))
    options = [NEW, str(chart), "-n", "farmer", "-f", str(path), "--no-hooks"]
    after = documents(run(["helm", "template", *options, "--is-upgrade", "--dry-run=server"]))
    scheduler_guard(before, after)
    if json.loads(run(["helm", "status", NEW, "-n", "farmer", "-o", "json"]))["version"] != status["version"]:
        raise ValueError("Replacement changed during activation")
    run(["helm", "upgrade", *options, "--atomic", "--wait", "--timeout", "3m"])
    scheduler_guard(before, documents(run(["helm", "get", "manifest", NEW, "-n", "farmer"])))
    return {"replacementSchedulerEnabled": True, "helmRevision": status["version"]+1}


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("pause-old", "start-replacement"))
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "pause-old":
        print(json.dumps(change_replicas(OLD, {"api": 0, "worker": 0, "beat": 0, "ui": 0}, args.directory)))
    else:
        old = json.loads(run(["kubectl", "-n", "farmer", "get", "deploy", "-o", "json"]))
        if any(d["metadata"]["name"].startswith(OLD + "-") and (d["spec"].get("replicas", 1) or d.get("status", {}).get("replicas", 0)) for d in old["items"]):
            raise ValueError("Old connector processes must stop first")
        print(json.dumps(change_replicas(NEW, {"api": 1, "worker": 1, "ui": 1}, args.directory)))
