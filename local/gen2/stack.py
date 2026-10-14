#!/usr/bin/env python3
"""Explicit local lifecycle commands; never resets DBs, seeds, or deletes volumes."""
import argparse
import json
import subprocess

from render import HERE, render

CORE = {"postgres": "openg2p-shared-postgres", "redis": "openg2p-shared-redis",
        "keycloak": "openg2p-shared-keycloak", "mailpit": "openg2p-shared-mailpit"}
OLD_COMMONS = (
    "farmer-registry-minio", "farmer-registry-iam-staff-api", "farmer-registry-awe-api",
    "farmer-registry-awe-ui", "farmer-registry-master-data-api", "farmer-registry-staff-portal-1",
    "platform-services-pm-staff-portal-api", "platform-services-pm-partner-api", "platform-services-pm-ui",
    "platform-services-cm-api", "platform-services-cm-ui",
)


def run(*args, capture=False):
    result = subprocess.run(list(args), check=True, text=True, encoding="utf-8",
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout if capture else None


def compose(project, *args):
    command = ["docker", "compose", "--env-file", str(HERE / ".env" if (HERE / ".env").exists() else HERE / ".env.example"),
               "-f", str(HERE / "generated" / (project + ".compose.json"))]
    return run(*command, *args)


def running():
    return set(run("docker", "ps", "--format", "{{.Names}}", capture=True).splitlines())


def shared_up(shared):
    live = running()
    missing = set(CORE.values()) - live
    if missing:
        raise RuntimeError("Start the existing shared base first: " + ", ".join(sorted(missing)))
    conflicts = live.intersection(OLD_COMMONS)
    if conflicts:
        raise RuntimeError("Old commons containers still running; follow the backed-up cutover in README.md: " + ", ".join(sorted(conflicts)))
    # Required volumes must exist, never silently create empty replacements.
    run("docker", "volume", "inspect", "openg2p-shared_postgres-data", "farmer-registry_minio-data", capture=True)
    networks = run("docker", "network", "ls", "--format", "{{.Name}}", capture=True).splitlines()
    if "openg2p-gen2" not in networks:
        run("docker", "network", "create", "openg2p-gen2")
    for alias, name in CORE.items():
        info = json.loads(run("docker", "inspect", name, capture=True))[0]
        if "openg2p-gen2" not in info["NetworkSettings"]["Networks"]:
            run("docker", "network", "connect", "--alias", alias, "openg2p-gen2", name)
    services = [n for n, s in shared["services"].items() if n not in CORE and not s.get("profiles")]
    # Existing base containers retain their config/network and other registries.
    compose("shared", "up", "-d", "--no-deps", "--wait", "--wait-timeout", "180", *services)


def require_queue_cutover():
    """Refuse to strand messages or duplicate consumers on the old broker."""
    for name in ("farmer-registry-celery-worker", "farmer-registry-celery-beat"):
        if name not in running():
            continue
        info = json.loads(run("docker", "inspect", name, capture=True))[0]
        if "openg2p-gen2" not in info["NetworkSettings"]["Networks"]:
            raise RuntimeError("Quiesce the old Farmer producers and drain its queue before cutover (README.md): " + name)
    for queue in ("farmer_registry_worker_queue", "celery"):
        count = run("docker", "exec", "openg2p-shared-redis", "redis-cli", "-n", "4", "LLEN", queue, capture=True).strip()
        if count != "0":
            raise RuntimeError("Old Farmer Redis DB 4 queue is not empty: " + queue)
    # Celery stores reserved/unacknowledged deliveries in a hash until ACK.
    count = run("docker", "exec", "openg2p-shared-redis", "redis-cli", "-n", "4", "HLEN", "unacked", capture=True).strip()
    if count != "0":
        raise RuntimeError("Old Farmer Redis DB 4 still contains unacknowledged deliveries")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("render", "validate", "shared-up", "setup", "build", "check", "farmer-up", "farmer-stop", "status"))
    args = parser.parse_args()
    shared, farmer = render(HERE / "generated")
    if args.command == "render":
        return
    if args.command == "validate":
        for name in ("shared", "farmer"):
            compose(name, "--profile", "*", "config", "--quiet")
        print("Both Compose projects validate; no engine or services started.")
        return
    # This fails before any lifecycle mutation if Docker is unavailable.
    run("docker", "info", "--format", "{{.ServerVersion}}", capture=True)
    if args.command == "shared-up":
        shared_up(shared)
    elif args.command == "setup":
        compose("shared", "run", "--rm", "--no-deps", "keycloak-init")
        compose("shared", "run", "--rm", "--no-deps", "minio-init")
        compose("shared", "run", "--rm", "--no-deps", "sync-login-provider")
        compose("shared", "run", "--rm", "--no-deps", "register-apps")
    elif args.command == "build":
        compose("farmer", "build", *[n for n, s in farmer["services"].items() if "build" in s])
    elif args.command in ("check", "farmer-up"):
        compose("farmer", "run", "--rm", "--no-deps", "preflight")
        if args.command == "farmer-up":
            require_queue_cutover()
            services = [n for n, s in farmer["services"].items() if not s.get("profiles")]
            compose("farmer", "up", "-d", "--wait", "--wait-timeout", "180", *services)
    elif args.command == "farmer-stop":
        compose("farmer", "--profile", "*", "stop")
    elif args.command == "status":
        for name in ("shared", "farmer"):
            compose(name, "--profile", "*", "ps", "--all")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Stopped: {error}")
        raise SystemExit(1)
