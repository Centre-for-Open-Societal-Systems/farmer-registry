#!/usr/bin/env python3
"""Back up the existing connector through its cluster; never print credentials.

Run on the trusted cluster host with its existing kubeconfig. The protected
destination must not exist. No scheduling, database or release changes occur.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ci/services"))
from coordinator import command  # noqa: E402
from connector_cutover import backup, sha
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ci"))
from environments import configuration, namespace, validate_cluster  # noqa: E402

EXPORT = '''import asyncio,json,os
import asyncpg
async def main():
 c=await asyncpg.connect(host=os.environ['CONNECTOR_DB_HOSTNAME'],port=int(os.environ['CONNECTOR_DB_PORT']),user=os.environ['CONNECTOR_DB_USERNAME'],password=os.environ['CONNECTOR_DB_PASSWORD'],database=os.environ['CONNECTOR_DB_DBNAME'])
 rows=await c.fetch('SELECT * FROM connector_definitions ORDER BY connector_id')
 print(json.dumps([dict(r) for r in rows],default=str))
 await c.close()
asyncio.run(main())
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=("dev", "staging"), required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    selected_namespace = namespace(args.environment)
    if args.environment == "staging":
        validate_cluster("staging", os.environ.get("KUBECONFIG_CREDENTIAL"),
                         json.loads(command(["kubectl", "config", "view", "--minify", "-o", "json"])))
    args.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    exports = args.directory / "exports"
    exports.mkdir(mode=0o700)
    deployment = json.loads(command(["kubectl", "get", "deploy", "farmer-connector-api", "-n", selected_namespace, "-o", "json"]))
    variables = {e["name"]: e.get("value") for c in deployment["spec"]["template"]["spec"]["containers"] for e in c.get("env", [])}
    database = variables["CONNECTOR_DB_DBNAME"]
    if args.environment == "staging" and database != configuration("staging")["legacyConnectorDatabase"]:
        raise ValueError("Wrong staging connector database")
    import re
    if not re.fullmatch(r"[a-z][a-z0-9_]+", database):
        raise ValueError("Unexpected database name")
    pods = json.loads(command(["kubectl", "get", "pods", "-n", "commons", "-l", "app.kubernetes.io/name=postgresql", "-o", "json"]))["items"]
    if len(pods) != 1:
        raise ValueError("Expected one Commons PostgreSQL pod")
    pg_pod = pods[0]["metadata"]["name"]
    # The final handoff snapshot is taken AFTER old API/worker/beat pods stop.
    # Read definitions through the existing PostgreSQL pod, not a live API pod.
    query = "SELECT coalesce(json_agg(row_to_json(c) ORDER BY connector_id),'[]'::json) FROM connector_definitions c"
    result = subprocess.run(["kubectl", "exec", "-n", "commons", pg_pod, "--", "sh", "-c",
                             'PGPASSWORD="$POSTGRES_POSTGRES_PASSWORD" exec psql -X -U postgres -d "$1" -Atc "$2"',
                             "inventory", database, query], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise ValueError("Pipeline inventory failed")
    rows = json.loads(result.stdout)
    documents = {"pipelines.json": rows,
                 "mappings.json": [{key: row.get(key) for key in ("connector_id", "data_model_mnemonic", "mapper_expression", "mapper_version")} for row in rows],
                 "checkpoints.json": [{key: row.get(key) for key in ("connector_id", "poll_state_json", "source_config_json")} for row in rows]}
    if args.environment == "staging":
        # Preserve actual statuses and correlation IDs. This export is never
        # used as an idempotency seed; the complete dump retains every table.
        query = "SELECT coalesce(json_agg(row_to_json(r) ORDER BY run_id),'[]'::json) FROM ingestion_runs r"
        documents["run-history.json"] = json.loads(command([
            "kubectl", "exec", "-n", "commons", pg_pod, "--", "sh", "-c",
            'PGPASSWORD="$POSTGRES_POSTGRES_PASSWORD" exec psql -X -U postgres -d "$1" -Atc "$2"',
            "inventory-runs", database, query]))
    for name, value in documents.items():
        (exports / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    pg_secret = json.loads(command(["kubectl", "get", "secret", "commons-postgresql", "-n", "commons", "-o", "json"]))
    password = base64.b64decode(pg_secret["data"]["postgres-password"])
    if b"\n" in password:
        raise ValueError("Unsupported credential encoding")
    dump = exports / "database.dump"
    with dump.open("wb") as output:
        result = subprocess.run(["kubectl", "exec", "-i", "-n", "commons", pg_pod, "--", "sh", "-c",
                                 'IFS= read -r PGPASSWORD; export PGPASSWORD; exec pg_dump -h 127.0.0.1 -U postgres -Fc --dbname "$1"', "backup", database],
                                input=password + b"\n", stdout=output, stderr=subprocess.PIPE, timeout=300)
    if result.returncode:
        raise ValueError("Database dump failed")
    def run(tool_args):
        if tool_args[0] == "pg_restore":
            # Kubernetes exec may keep stdin open after the local file ends.
            # Bound the TOC input explicitly; --list validates the directory,
            # while the required full restore rehearsal validates payload data.
            remote_file = "/tmp/coss-connector-backup-toc-" + uuid.uuid4().hex
            with Path(tool_args[-1]).open("rb") as file:
                prefix = file.read(2 * 1024 * 1024)
            result = subprocess.run(["kubectl", "exec", "-i", "-n", "commons", pg_pod, "--", "sh", "-c",
                                     'umask 077; head -c "$1" > "$2"; pg_restore --list "$2"; result=$?; rm -f "$2"; exit "$result"',
                                     "validate-backup", str(len(prefix)), remote_file],
                                    input=prefix, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60)
            if result.returncode:
                raise ValueError("Database dump directory invalid")
            return ""
        return command(tool_args)
    snapshot = args.directory / "snapshot"
    backup(snapshot, {name: exports / name for name in (*documents, "database.dump")}, run, args.environment)
    print(json.dumps({"directory": str(snapshot), "backupHash": sha(snapshot / "backup.json"),
                      "pipelines": len(rows), "databaseBytes": dump.stat().st_size}))


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except Exception:
        print("FAIL: inventory stopped; private command output withheld", file=sys.stderr)
        raise SystemExit(1)
