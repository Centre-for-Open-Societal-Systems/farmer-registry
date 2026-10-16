"""Copy the retained dev snapshot over authenticated SSH; never archive in CI."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ci/services"))
from connector_cutover import verify_backup  # noqa: E402

FILES = {"backup.json", "values.yaml", "manifest.yaml", "hooks.yaml", "pipelines.json",
         "mappings.json", "checkpoints.json", "database.dump"}
REMOTE = "/var/backups/farmer-connector-20261015-before-replacement/snapshot-validated"
PHASE = "configuration"


def main():
    global PHASE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--ssh-key", type=Path, required=True)
    args = parser.parse_args()
    args.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    expected = yaml.safe_load((ROOT / "helm/environments/dev/services/registry-connector.yaml").read_text())["_coordination"]["backupHash"]
    known_hosts = ROOT / "scripts/operations/connector/new-dev-known-hosts"
    PHASE = "authenticated-ssh-transfer"
    process = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                                "-o", "UserKnownHostsFile=" + str(known_hosts), "-o", "ConnectTimeout=15",
                                "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
                                "-i", str(args.ssh_key), "ubuntu@13.201.58.55",
                                "sudo -n tar -C " + REMOTE + " -cf - ."], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        found = set()
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for entry in archive:
                if entry.isdir() and entry.name in (".", "./"):
                    continue
                name = entry.name.removeprefix("./")
                if name not in FILES or name in found or not entry.isfile():
                    raise ValueError("Unexpected backup archive member")
                found.add(name)
                destination = args.directory / name
                with destination.open("xb") as output, archive.extractfile(entry) as source:
                    shutil.copyfileobj(source, output)
                destination.chmod(0o600)
        # Consume tar padding before waiting, so a full SSH stdout pipe cannot
        # hold the sender open after tarfile has reached the archive terminator.
        while process.stdout.read(1024 * 1024):
            pass
        PHASE = "snapshot-integrity"
        if process.wait(timeout=30) or found != FILES or verify_backup(args.directory) != expected:
            raise ValueError("Backup is unavailable or its integrity changed")
    finally:
        if process.poll() is None:
            process.terminate(); process.wait(timeout=10)
    print(json.dumps({"backupVerified": True, "backupHash": expected}))


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except Exception as exc:
        print("Backup transfer stopped during " + PHASE + " (" + type(exc).__name__ + "); private output withheld", file=sys.stderr)
        raise SystemExit(1)
