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
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ci"))
from environments import configuration, namespace, validate_cluster

import yaml

OLD = "farmer-connector"
NEW = "farmer-registry-connector"


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError("Connector Helm operation failed; private output withheld")
    return result.stdout


def release_status(release, environment):
    selected_namespace = namespace(environment)
    status = json.loads(run(["helm", "status", release, "-n", selected_namespace, "-o", "json"]))
    if (status.get("name"), status.get("namespace"), status.get("info", {}).get("status")) != (release, selected_namespace, "deployed"):
        raise ValueError("Connector release does not match the selected environment")
    if type(status.get("version")) is not int or status["version"] < 1:
        raise ValueError("Connector release revision required")
    return status


def documents(raw):
    return [item for item in yaml.safe_load_all(raw) if item]


def replica_guard(before, after, release, replicas, environment="dev"):
    def index(items):
        if any(d["metadata"].get("namespace", namespace(environment)) != namespace(environment) for d in items):
            raise ValueError("Replica handoff crosses the selected environment")
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


def export_chart(release, version, directory, environment="dev"):
    selected_namespace = namespace(environment)
    secret = json.loads(run(["kubectl", "-n", selected_namespace, "get", "secret",
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
    for item in chart.get("files") or []:
        relative = Path(item["name"])
        if relative.is_absolute() or ".." in relative.parts or relative.name in ("Chart.yaml", "values.yaml"):
            raise ValueError("Invalid installed chart file path")
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(item["data"]))
    return saved


def route_guard(before, after, new_route=False, environment="dev"):
    if any(d["metadata"].get("namespace", namespace(environment)) != namespace(environment) for d in before + after):
        raise ValueError("Route handoff crosses the selected environment")
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
    if route["hosts"] != [configuration(environment)["connectorHostname"]] or route["gateways"] != ["internal"]:
        raise ValueError("Connector routing environment changed")
    for item in route["http"]:
        if len(item["route"]) != 1: raise ValueError("Unexpected connector route")
        destination = item["route"][0]["destination"]
        if destination["host"] not in (NEW+"-api", NEW+"-ui"):
            raise ValueError("Connector must route only to its replacement services")
        if not new_route:
            destination["host"] = destination["host"].replace(NEW, OLD, 1)
    if old != new: raise ValueError("Routing handoff would change unrelated resources")


def handoff_route(directory, new_route=False, environment="dev"):
    selected_namespace = namespace(environment)
    release = NEW if new_route else OLD
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    status = release_status(release, environment)
    before = documents(run(["helm", "get", "manifest", release, "-n", selected_namespace]))
    values = yaml.safe_load(run(["helm", "get", "values", release, "-n", selected_namespace, "-o", "yaml"]))
    chart = directory / "chart"; export_chart(release, status["version"], chart, environment)
    if new_route:
        old_values = yaml.safe_load(run(["helm", "get", "values", OLD, "-n", selected_namespace, "-o", "yaml"]))
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
    options = [release, str(chart), "-n", selected_namespace, "-f", str(path), "--no-hooks"]
    after = documents(run(["helm", "template", *options, "--is-upgrade", "--dry-run=server"]))
    route_guard(before, after, new_route, environment)
    if release_status(release, environment)["version"] != status["version"]:
        raise ValueError("Connector changed during route handoff")
    run(["helm", "upgrade", *options, "--atomic", "--wait", "--timeout", "3m"])
    route_guard(before, documents(run(["helm", "get", "manifest", release, "-n", selected_namespace])), new_route, environment)
    return {"routeOwner": release, "helmRevision": status["version"]+1, "destination": NEW}


def change_replicas(release, replicas, directory, environment="dev"):
    selected_namespace = namespace(environment)
    if release not in (OLD, NEW):
        raise ValueError("Unknown connector owner")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    status = release_status(release, environment)
    if status["info"]["status"] != "deployed":
        raise ValueError("Deployed connector release required")
    before_raw = run(["helm", "get", "manifest", release, "-n", selected_namespace])
    before = documents(before_raw)
    (directory / "before.yaml").write_text(before_raw)
    values = yaml.safe_load(run(["helm", "get", "values", release, "-n", selected_namespace, "-o", "yaml"]))
    (directory / "original-values.yaml").write_text(yaml.safe_dump(values))
    chart = directory / "chart"
    export_chart(release, status["version"], chart, environment)
    # Existing old init dependency resources are retained verbatim; no chart
    # download or setup rerun is involved in stopping scheduling/processing.
    values.setdefault("postgres-init", {})["enabled"] = False
    for role, count in replicas.items():
        values.setdefault(role, {})["replicaCount"] = count
    path = directory / "values.yaml"
    path.write_text(yaml.safe_dump(values))
    base = ["helm", "template", release, str(chart), "-n", selected_namespace, "-f", str(path), "--is-upgrade", "--dry-run=server", "--no-hooks"]
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
    replica_guard(before, after, release, replicas, environment)
    current = release_status(release, environment)
    if current["version"] != status["version"]:
        raise ValueError("Connector changed during handoff")
    run(["helm", "upgrade", release, str(chart), "-n", selected_namespace, "-f", str(path),
         "--no-hooks", "--atomic", "--wait", "--timeout", "3m"])
    replica_guard(before, documents(run(["helm", "get", "manifest", release, "-n", selected_namespace])), release, replicas, environment)
    final = release_status(release, environment)
    return {"release": release, "helmRevision": final["version"], "replicas": replicas,
            "privateRecoveryDirectory": str(directory), "setupJobsExecuted": False}


def scheduler_guard(before, after, environment="dev"):
    if any(d["metadata"].get("namespace", namespace(environment)) != namespace(environment) for d in before + after):
        raise ValueError("Scheduler handoff crosses the selected environment")
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


def activate_scheduler(directory, checkpoint_evidence, environment="dev"):
    selected_namespace = namespace(environment)
    if environment == "staging":
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ci/deploy"))
        from staging import ACCEPTANCE, passed
        if checkpoint_evidence.get("environment") != "staging":
            raise ValueError("Staging scheduler evidence belongs to another environment")
        passed(checkpoint_evidence, tuple(k for k in ACCEPTANCE if k not in (
            "singleScheduler", "automaticPollNoDuplicates", "temporaryResourcesExportedAndRemoved")))
        old = json.loads(run(["kubectl", "-n", selected_namespace, "get", "deploy", "-o", "json"]))
        if any(d["metadata"]["name"].startswith(OLD + "-") and
               (d["spec"].get("replicas", 1) or d.get("status", {}).get("replicas", 0)) for d in old["items"]):
            raise ValueError("Old staging connector processes must remain stopped")
    if checkpoint_evidence.get("checkpointReconciled") is not True or checkpoint_evidence.get("pipelinesPaused") is not True:
        raise ValueError("Final checkpoint evidence required")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    status = release_status(NEW, environment)
    if environment == "staging" and checkpoint_evidence.get("helmRevision") != status.get("version"):
        raise ValueError("Staging connector changed after manual intake acceptance")
    before = documents(run(["helm", "get", "manifest", NEW, "-n", selected_namespace]))
    values = yaml.safe_load(run(["helm", "get", "values", NEW, "-n", selected_namespace, "-o", "yaml"]))
    chart = directory / "chart"
    export_chart(NEW, status["version"], chart, environment)
    values["beat"]["enabled"] = True
    values["beat"]["replicaCount"] = 1
    values["cossCutover"] = {"phase": "active", "checkpointBackupHash": checkpoint_evidence["snapshotHash"]}
    path = directory / "values.yaml"; path.write_text(yaml.safe_dump(values))
    options = [NEW, str(chart), "-n", selected_namespace, "-f", str(path), "--no-hooks"]
    after = documents(run(["helm", "template", *options, "--is-upgrade", "--dry-run=server"]))
    scheduler_guard(before, after, environment)
    if release_status(NEW, environment)["version"] != status["version"]:
        raise ValueError("Replacement changed during activation")
    run(["helm", "upgrade", *options, "--atomic", "--wait", "--timeout", "3m"])
    scheduler_guard(before, documents(run(["helm", "get", "manifest", NEW, "-n", selected_namespace])), environment)
    return {"replacementSchedulerEnabled": True, "helmRevision": status["version"]+1}


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=("dev", "staging"), required=True)
    parser.add_argument("action", choices=("pause-old", "start-replacement", "activate-scheduler", "handoff-route"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path)
    args = parser.parse_args()
    selected_namespace = namespace(args.environment)
    if args.environment == "staging":
        validate_cluster("staging", os.environ.get("KUBECONFIG_CREDENTIAL"),
                         json.loads(run(["kubectl", "config", "view", "--minify", "-o", "json"])))
    if args.action == "pause-old":
        print(json.dumps(change_replicas(OLD, {"api": 0, "worker": 0, "beat": 0, "ui": 0}, args.directory, args.environment)))
    elif args.action == "activate-scheduler":
        if not args.acceptance: parser.error("Scheduler activation requires acceptance evidence")
        print(json.dumps(activate_scheduler(args.directory, json.loads(args.acceptance.read_text()), args.environment)))
    elif args.action == "handoff-route":
        if args.environment == "staging":
            if not args.acceptance: parser.error("Staging routing requires acceptance evidence")
            review = json.loads(args.acceptance.read_text())
            if review.get("environment") != "staging" or review.get("helmRevision") != release_status(NEW, "staging")["version"]:
                raise ValueError("Routing evidence must cover the current staging connector")
            sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ci/deploy"))
            from staging import ACCEPTANCE, passed
            passed(review, ACCEPTANCE)
        print(json.dumps(handoff_route(args.directory, new_route=True, environment=args.environment)))
    else:
        if args.environment == "staging":
            if not args.acceptance: parser.error("Replacement startup requires stopped-state reconciliation evidence")
            review = json.loads(args.acceptance.read_text())
            if review.get("environment") != "staging" or review.get("helmRevision") != release_status(NEW, "staging")["version"]:
                raise ValueError("Startup evidence must cover the current staging connector")
            if any(review.get(k) is not True for k in ("pipelinesPaused", "pipelinesAndMappingsMigrated", "checkpointsReconciled", "oldQueueDrained", "signingKeyRegistered")):
                raise ValueError("Complete stopped-state reconciliation is required")
        old = json.loads(run(["kubectl", "-n", selected_namespace, "get", "deploy", "-o", "json"]))
        if any(d["metadata"]["name"].startswith(OLD + "-") and (d["spec"].get("replicas", 1) or d.get("status", {}).get("replicas", 0)) for d in old["items"]):
            raise ValueError("Old connector processes must stop first")
        print(json.dumps(change_replicas(NEW, {"api": 1, "worker": 1, "ui": 1}, args.directory, args.environment)))
