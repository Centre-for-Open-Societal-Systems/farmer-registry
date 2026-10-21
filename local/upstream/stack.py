"""Local RC trial: independently owned Commons Base, Services and Registry.

No command connects to the dev server or to the original local stack.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NETWORK = "farmer-upstream-trial"
BASE = {"postgres", "redis", "minio", "minio-init", "keycloak", "keycloak-init", "kafka"}
REGISTRY = {"id-generator", "queue", "sanity", "farmer-registry-staff-api",
            "farmer-registry-partner-api", "farmer-registry-celery-worker",
            "farmer-registry-celery-beat", "farmer-registry-staff-ui", "farmer-registry-db-seed"}
PROJECTS = {"base": "farmer-upstream-commons-base",
            "services": "farmer-upstream-commons-services",
            "registry": "farmer-upstream-registry"}
# Keep the trial volumes created during bootstrap; never attach original data.
VOLUMES = {n: "farmer-upstream-trial_" + n for n in
           ("postgres-data", "minio-data", "queue-data", "kafka-data")}


def run(*args):
    subprocess.run(args, check=True)


def render():
    source = json.loads((HERE / "compose.template.json").read_text(encoding="utf-8").replace("@ROOT@", ROOT.as_posix()))
    groups = {"base": BASE, "registry": REGISTRY,
              "services": set(source["services"]) - BASE - REGISTRY}
    for group, owned in groups.items():
        services = {n: copy.deepcopy(s) for n, s in source["services"].items() if n in owned}
        used = set()
        for s in services.values():
            s["depends_on"] = {n: v for n, v in s.get("depends_on", {}).items() if n in owned}
            for mount in s.get("volumes", []):
                if mount.split(":")[0] in VOLUMES:
                    used.add(mount.split(":")[0])
        doc = {"name": PROJECTS[group], "services": services,
               "networks": {"default": {"external": True, "name": NETWORK}},
               "volumes": {n: {"external": True, "name": VOLUMES[n]} for n in used}}
        (HERE / "generated").mkdir(exist_ok=True)
        (HERE / "generated" / (group + ".compose.json")).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return groups


def compose(group, *args):
    run("docker", "compose", "-f", str(HERE / "generated" / (group + ".compose.json")), *args)


def infra():
    if subprocess.run(["docker", "network", "inspect", NETWORK], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        run("docker", "network", "create", NETWORK)
    for volume in VOLUMES.values():
        run("docker", "volume", "create", volume)


def up(group, groups):
    if group == "registry" and (HERE / "generated" / "geo-migration-recovery.json").exists():
        raise RuntimeError("Reconcile the pending geography recovery journal before starting Registry")
    config = json.loads((HERE / "generated" / (group + ".compose.json")).read_text())
    names = [n for n in groups[group] if not config["services"][n].get("profiles")]
    compose(group, "up", "-d", "--wait", "--wait-timeout", "180", *sorted(names))


def seed():
    config = json.loads((HERE / "generated" / "registry.compose.json").read_text())
    running = []
    for name, service in config['services'].items():
        if service.get('profiles'):
            continue
        result = subprocess.run(['docker', 'inspect', '--format', '{{.State.Running}}',
                                 service['container_name']], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip() == 'true':
            running.append(name)
    if running:
        compose('registry', 'stop', *running)
    # Leave writers stopped on failure, including a pending recovery journal.
    compose("services", "run", "--rm", "--no-deps", "coss-geo-seed")
    compose("registry", "run", "--rm", "--no-deps", "farmer-registry-db-seed")
    if running:
        compose('registry', 'up', '-d', '--wait', '--wait-timeout', '180', *running)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["render", "validate", "infra", "build", "init", "seed", "test", "up", "stop", "status", "reset"])
    p.add_argument("group", choices=[*PROJECTS, "all"], nargs="?", default="all")
    p.add_argument("--confirm-trial-reset", action="store_true")
    args = p.parse_args()
    groups = render()
    selected = list(PROJECTS) if args.group == "all" else [args.group]
    if args.command in {"init", "seed", "test"} and args.group != "all":
        p.error(f"{args.command} operates across project boundaries; use group all")
    if args.command == "render":
        return
    if args.command == "validate":
        for group in selected:
            compose(group, "--profile", "*", "config", "--quiet")
    elif args.command == "infra":
        infra()
    elif args.command == "build":
        for group in selected:
            compose(group, "--profile", "*", "build")
    elif args.command == "init":
        infra()
        compose("registry", "--profile", "*", "build")
        up("base", groups)
        for service in ("minio-init", "keycloak-init"):
            compose("base", "run", "--rm", "--no-deps", service)
        up("services", groups)
        for service in ("sync-login-provider", "register-apps"):
            compose("services", "run", "--rm", "--no-deps", service)
        # Stock API startup does not propagate migration failures; check explicitly.
        compose("registry", "run", "--rm", "--no-deps", "--entrypoint", "python",
                "farmer-registry-staff-api", "-m", "openg2p_registry_staff_api.main", "migrate")
        seed()
        up("registry", groups)
    elif args.command == "seed":
        seed()
    elif args.command == "test":
        compose("registry", "run", "--rm", "--no-deps", "--env-from-file",
                str(HERE / "sanity.env.example"), "--entrypoint", "pytest", "sanity", "-v",
                "tests/test_smoke.py", "tests/test_e2e_negative.py", "tests/test_e2e_dci.py",
                "tests/test_e2e_change_request.py", "tests/test_e2e_intake.py")
    elif args.command == "up":
        for group in selected:
            up(group, groups)
    elif args.command == "stop":
        for group in reversed(selected):
            compose(group, "--profile", "*", "stop")
    elif args.command == "status":
        for group in selected:
            compose(group, "--profile", "*", "ps", "--all")
    elif args.command == "reset":
        if not args.confirm_trial_reset or args.group != "all":
            p.error("reset requires all --confirm-trial-reset; it deletes only fresh trial data")
        for group in reversed(list(PROJECTS)):
            compose(group, "--profile", "*", "down")
        for volume in VOLUMES.values():
            assert volume.startswith("farmer-upstream-trial_")
            run("docker", "volume", "rm", volume)


if __name__ == "__main__":
    main()
