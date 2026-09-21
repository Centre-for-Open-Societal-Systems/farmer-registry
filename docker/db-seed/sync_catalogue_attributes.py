#!/usr/bin/env python3
"""Sync select agriculture code lists from catalogue-service into the
registry's own g2p_attribute_values.

Why this exists, and why it is separate from load_attributes_from_mds.py
--------------------------------------------------------------------------
load_attributes_from_mds.py already syncs code lists, but from Master Data's
G2P-envelope API (POST /attributes/get_all_attributes). catalogue-service
exposes a different, plain-REST shape (GET /v1/catalogues/{code}/values) and
its read endpoints require an IAM-issued token, which a seed-time script has
no natural way to obtain. Reading catalogue-service's own Postgres directly
sidesteps both problems and mirrors how the geo hierarchy was inspected.

Why merge-only, unlike load_attributes_from_mds.py's supersede-on-conflict
--------------------------------------------------------------------------
load_attributes_from_mds.py treats the incoming pack as authoritative and
deletes whatever it doesn't redefine. That's correct when MDS is the single
source of truth for a list. It is NOT correct here: LIVESTOCK_TYPE already
holds Odoo's 8-species list (matched 1:1 in the parity audit), while the
catalogue's version is a different, narrower 5-value taxonomy that also adds
"beehive" (not livestock in the Odoo sense). Superseding would drop
CHICKEN/DONKEY/HORSE/MULE out from under any farmer record already using
them. So: add whatever normalizes to a code that isn't already present,
never touch or remove what's already there.

LIVESTOCK_BREED is deliberately not in DOMAIN_MAP. The existing 3 rows
(IMPROVED/LOCAL/HYBRID) are a classification tier; the catalogue's 94 rows
are actual named breeds (Boran, Horro, ...). Mixing them into one dropdown
conflates two different questions — needs a product decision (new field vs.
replace) before syncing, not a data merge.

Env
---
  CATALOGUE_PGHOST / CATALOGUE_PGPORT / CATALOGUE_PGDATABASE /
  CATALOGUE_PGUSER / CATALOGUE_PGPASSWORD   — the catalogue-service database
  PGHOST / PGPORT / PGDATABASE / PGUSER / PGPASSWORD  — the registry database
  CATALOGUE_RELEASE_ID  — optional; defaults to the ACTIVE release

Usage
-----
  python3 sync_catalogue_attributes.py
"""

import os
import re
import sys

import psycopg2
from psycopg2.extras import execute_values

# catalogue "code" -> (registry attribute_id, registry value_id prefix)
DOMAIN_MAP = {
    "crop": ("CROP_COMMODITY", "CROP"),
    "livestock_type": ("LIVESTOCK_TYPE", "LSTK"),
    "livestock_gender": ("LIVESTOCK_GENDER", "LGENDER"),
    "livestock_body_condition": ("LIVESTOCK_BODY_CONDITION", "LBCOND"),
    "livestock_production_type": ("LIVESTOCK_PRODUCTION_TYPE", "LPTYPE"),
}


def log(msg):
    print(f"[catalogue-sync] {msg}", flush=True)


def die(msg):
    print(f"[catalogue-sync] ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def normalize(name):
    """Scientific-name-stripped, upper-snake code — matches the existing
    hand-seeded convention (WHEAT, MALT_BARLEY, ...)."""
    s = re.sub(r"\([^)]*\)", "", name)
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s.upper()


def clean_display(name):
    s = re.sub(r"\([^)]*\)", "", name)
    s = re.sub(r"\s+", " ", s).strip()
    return s.title() if s else name.strip()


def catalogue_conn():
    return psycopg2.connect(
        host=os.environ["CATALOGUE_PGHOST"],
        port=os.environ.get("CATALOGUE_PGPORT", "5432"),
        dbname=os.environ["CATALOGUE_PGDATABASE"],
        user=os.environ["CATALOGUE_PGUSER"],
        password=os.environ.get("CATALOGUE_PGPASSWORD", ""),
    )


def registry_conn():
    return psycopg2.connect(
        host=os.environ["PGHOST"],
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ.get("PGPASSWORD", ""),
    )


def resolve_release_id(cat_cur):
    release_id = os.environ.get("CATALOGUE_RELEASE_ID")
    if release_id:
        return release_id
    cat_cur.execute(
        "SELECT release_id FROM catalogue_releases WHERE status = 'ACTIVE' "
        "ORDER BY activated_at DESC LIMIT 1"
    )
    row = cat_cur.fetchone()
    if not row:
        return None
    return row[0]


def sync_domain(cat_cur, reg_conn, catalogue_code, attribute_id, prefix, release_id):
    cat_cur.execute(
        """
        SELECT v.code, v.display_name FROM catalogue_values v
        JOIN catalogues c ON c.catalogue_id = v.catalogue_id
        WHERE c.code = %s AND c.release_id = %s AND v.status = 'ACTIVE'
        ORDER BY v.sort_order
        """,
        (catalogue_code, release_id),
    )
    catalogue_rows = cat_cur.fetchall()

    with reg_conn.cursor() as rcur:
        rcur.execute(
            "SELECT value_code FROM g2p_attribute_values WHERE attribute_id = %s",
            (attribute_id,),
        )
        seen = {r[0] for r in rcur.fetchall()}
        existing_count = len(seen)
        rcur.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM g2p_attribute_values WHERE attribute_id = %s",
            (attribute_id,),
        )
        next_order = rcur.fetchone()[0] + 1

    new_rows = []
    for _raw_code, display_name in catalogue_rows:
        norm = normalize(display_name)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        new_rows.append(
            (f"{prefix}_{norm}", attribute_id, norm, clean_display(display_name), None, next_order)
        )
        next_order += 1

    if not new_rows:
        log(f"{attribute_id}: nothing new ({len(catalogue_rows)} in catalogue, {existing_count} already present)")
        return

    with reg_conn.cursor() as rcur:
        execute_values(
            rcur,
            """
            INSERT INTO g2p_attribute_values
              (value_id, attribute_id, value_code, value_display, parent_value_id, sort_order)
            VALUES %s
            ON CONFLICT (value_id) DO NOTHING
            """,
            new_rows,
        )
    reg_conn.commit()
    log(f"{attribute_id}: added {len(new_rows)} new value(s) ({existing_count} pre-existing left untouched)")


def main():
    cat_conn = catalogue_conn()
    reg_conn = registry_conn()
    try:
        with cat_conn.cursor() as cat_cur:
            release_id = resolve_release_id(cat_cur)
            if not release_id:
                log("no ACTIVE catalogue release found; nothing to sync")
                return
            log(f"syncing from catalogue release {release_id}")

            for catalogue_code, (attribute_id, prefix) in DOMAIN_MAP.items():
                sync_domain(cat_cur, reg_conn, catalogue_code, attribute_id, prefix, release_id)
    finally:
        cat_conn.close()
        reg_conn.close()


if __name__ == "__main__":
    main()
