"""Fail-fast COSS configuration installer for fresh RC trial databases.

Keeps a checksum ledger per database. Identical reruns skip applied SQL;
changed SQL is rejected rather than overwriting existing operator configuration.
"""
import hashlib
import os
import re
from pathlib import Path
import subprocess

import psycopg2


def apply(database, files):
    with psycopg2.connect(host=os.environ["PGHOST"], port=os.getenv("PGPORT", "5432"),
                          dbname=database, user=os.environ["PGUSER"], password=os.environ["PGPASSWORD"]) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS coss_trial_seed_ledger (path text PRIMARY KEY, sha256 text NOT NULL)")
            for file in files:
                text = file.read_text(encoding="utf-8")
                # Upstream keeps comment-only placeholder files in metadata.
                if not re.sub(r"--[^\n]*|/\*.*?\*/", "", text, flags=re.S).strip():
                    continue
                if file.suffix == ".tpl":
                    for key in ("AWE_CALLBACK_HMAC_SECRET", "AWE_CALLBACK_SECRET_ID", "AWE_CALLBACK_CALLER_SERVICE"):
                        text = text.replace("${" + key + "}", os.environ[key].replace("'", "''"))
                digest = hashlib.sha256(text.encode()).hexdigest()
                key = file.relative_to(Path("/seed")).as_posix()
                cur.execute("SELECT sha256 FROM coss_trial_seed_ledger WHERE path=%s", (key,))
                existing = cur.fetchone()
                if existing:
                    if existing[0] != digest:
                        raise RuntimeError(f"Changed applied seed {key}: use an explicit migration or reset the trial")
                    print("unchanged", database, key, flush=True)
                    continue
                print("apply", database, key, flush=True)
                cur.execute(text)
                cur.execute("INSERT INTO coss_trial_seed_ledger VALUES (%s,%s)", (key, digest))


def main():
    lookup = Path("/seed/meta_data/lookup-data")
    # Reference lists belong to MDS in rc.544, with attribute definitions first.
    apply(os.environ["MD_PGDATABASE"], sorted(lookup.glob("g2p_attributes*.sql")) + sorted(lookup.glob("g2p_attribute_values*.sql")))
    apply(os.environ["PGDATABASE"], [p for p in sorted(Path("/seed/meta_data").rglob("*.sql")) if "lookup-data" not in p.parts])
    apply(os.environ["AWE_PGDATABASE"], sorted(Path("/seed/awe_meta_data").glob("*.sql")) + sorted(Path("/seed/awe_meta_data").glob("*.tpl")))
    subprocess.run(["python", "/seed/sync_geo_widgets.py"], check=True)
    subprocess.run(["python", "/seed/upload_templates.py"], check=True)


if __name__ == "__main__":
    main()
