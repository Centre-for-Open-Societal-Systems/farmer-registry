#!/usr/bin/env python3
"""Load the real Ethiopia geo hierarchy into the Master Data Postgres.

Overrides the base db-seed image's own load_geo_data.py (which loads a
generic/fictional sample pack — "Kamuntu" region names — from openg2p-data's
geo.csv). Farmer Registry is Ethiopia-specific, so this loads a static
snapshot of the real administrative hierarchy instead: region -> zone ->
woreda -> kebele, sourced from catalogue-service (the ETH-catalogue-v8
release) and baked into this image at build time as
seed-data/geo/geo_levels.json and geo_level_values.json.

Baked in as a static snapshot rather than fetched live from catalogue-service
at deploy time deliberately: catalogue-service is a separate service on its
own network/lifecycle (its own Docker Hub image, docker.io/rediet03/mdm),
not guaranteed reachable from wherever db-seed runs, and administrative
boundaries change rarely enough that a snapshot is the right tradeoff over a
live cross-service dependency during every deployment.

level_value_mnemonic is set equal to display_name (e.g. "Tigray", not a
code like "et01" or "ET01") — the staff-ui's geo-hierarchy dropdown widget
renders the mnemonic directly with no separate label field, so this is what
actually needs to hold the human-readable name for the dropdown to be usable.
pcode carries the real administrative P-code (e.g. "ET01") separately, should
anything need the code-based join key instead of the display value.

Same DB connection convention (MD_PG*) and ON CONFLICT DO NOTHING
idempotency as the file this replaces, so re-running (upgrade, restart,
Helm post-upgrade hook) is safe.
"""

import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

SEED_DIR = Path(os.environ.get("GEO_SEED_DIR", "/seed/seed-data/geo"))
LEVELS_FILE = SEED_DIR / "geo_levels.json"
VALUES_FILE = SEED_DIR / "geo_level_values.json"


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        print(f"[load-geo-data] Missing env var: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def _read_json(path: Path) -> list:
    if not path.is_file():
        print(f"[load-geo-data] Missing file: {path}", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def insert_geo_levels(cur, rows: list) -> int:
    execute_values(
        cur,
        """
        INSERT INTO g2p_geo_levels
            (level_id, level_mnemonic, parent_level_id, display_name, version, valid_from, valid_to)
        VALUES %s
        ON CONFLICT (level_id) DO NOTHING
        """,
        [
            (
                r["level_id"], r["level_mnemonic"], r["parent_level_id"],
                r.get("display_name"), r.get("version"), r.get("valid_from"), r.get("valid_to"),
            )
            for r in rows
        ],
    )
    return len(rows)


def insert_geo_level_values(cur, rows: list) -> int:
    execute_values(
        cur,
        """
        INSERT INTO g2p_geo_level_values
            (level_value_id, level_id, level_value_mnemonic, parent_level_value_id,
             pcode, pcode_source, display_name, version)
        VALUES %s
        ON CONFLICT (level_value_id) DO NOTHING
        """,
        [
            (
                r["level_value_id"], r["level_id"],
                r.get("display_name") or r["level_value_mnemonic"],  # mnemonic = display name; see module docstring
                r.get("parent_level_value_id"), r.get("pcode"), r.get("pcode_source"),
                r.get("display_name"), r.get("version"),
            )
            for r in rows
        ],
        page_size=1000,
    )
    return len(rows)


def main() -> None:
    levels = _read_json(LEVELS_FILE)
    values = _read_json(VALUES_FILE)

    conn = psycopg2.connect(
        host=env("MD_PGHOST"),
        port=os.environ.get("MD_PGPORT", "5432"),
        dbname=env("MD_PGDATABASE"),
        user=env("MD_PGUSER"),
        password=env("MD_PGPASSWORD"),
    )
    try:
        with conn:
            with conn.cursor() as cur:
                n = insert_geo_levels(cur, levels)
                print(f"[load-geo-data] g2p_geo_levels: {n} rows")
                n = insert_geo_level_values(cur, values)
                print(f"[load-geo-data] g2p_geo_level_values: {n} rows")
    finally:
        conn.close()
    print("[load-geo-data] Completed.")


if __name__ == "__main__":
    main()
