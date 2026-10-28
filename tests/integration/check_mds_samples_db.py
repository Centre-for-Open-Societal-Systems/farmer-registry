"""Disposable PostgreSQL check using the companion openg2p-data country pack.

MDS_SAMPLE_TEST_DSN must identify a database named mds_seed_test*. This creates
and drops only a unique test schema. It exercises the real reader and SQL, not
the MDS loader, registry API, AWE or Celery.
"""
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docker/db-seed"))
from master_data_samples import load_samples


def main():
    dsn = os.environ["MDS_SAMPLE_TEST_DSN"]
    pack = Path(os.environ["MDS_SAMPLE_TEST_PACK"])
    conn = psycopg2.connect(dsn)
    assert conn.info.dbname.startswith("mds_seed_test"), "Use a disposable test database"
    schema = "seed_contract_" + uuid4().hex
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cur.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            for kind in ("individuals", "households"):
                rows = json.loads((pack / "samples" / f"{kind}.json").read_text(encoding="utf-8"))
                for row in rows:
                    row["country"] = "ETH"
                fields = sorted(set().union(*(row.keys() for row in rows)))
                types = {key: "integer" if key in ("age", "birth_year", "size_total") else
                         "jsonb" if key == "address_parts" else
                         "double precision" if key in ("latitude", "longitude") else "text" for key in fields}
                table = "g2p_sample_" + kind
                cur.execute(sql.SQL("CREATE TABLE {} ({})").format(sql.Identifier(table),
                    sql.SQL(",").join(sql.SQL("{} {}").format(sql.Identifier(k),sql.SQL(types[k])) for k in fields)))
                insert = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(sql.Identifier(table),
                    sql.SQL(",").join(map(sql.Identifier,fields)),sql.SQL(",").join(sql.Placeholder() for _ in fields))
                cur.executemany(insert, [[Json(row[k]) if isinstance(row.get(k),dict) else row.get(k) for k in fields] for row in rows])
            cur.execute("CREATE TABLE g2p_list_versions (list_id text,version_no integer,list_code text,status text,effective_from timestamptz)")
            cur.execute("CREATE TABLE g2p_list_version_values (list_id text,version_no integer,value_code text,roles jsonb,status text)")
            for folder in (pack / "codelists", pack / "domains"):
                for path in folder.rglob("*.json"):
                    doc = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(doc,dict) or "attribute_id" not in doc: continue
                    key = doc["attribute_id"]
                    cur.execute("INSERT INTO g2p_list_versions VALUES (%s,1,%s,'PUBLISHED',NULL)", (key,doc["attribute_code"]))
                    cur.executemany("INSERT INTO g2p_list_version_values VALUES (%s,1,%s,%s,'ACTIVE')",
                        [(key,v["value_code"],Json(v.get("roles",[]))) for v in doc["values"]])
            # Neither a draft nor a future published version is in effect.
            cur.execute("INSERT INTO g2p_list_versions VALUES ('GENDER',2,'GENDER','DRAFT',NULL),('GENDER',3,'GENDER','PUBLISHED',now()+interval '1 day')")
        geo = {v["level_value_id"] for v in json.loads((pack / "values.json").read_text(encoding="utf-8"))}
        def connect(): return psycopg2.connect(dsn, options="-c search_path=" + schema)
        people, households = load_samples(connect, geo)
        assert len(people) == 21 and len(households) == 6
        assert sum(len(h["members"]) for h in households) == 21
        with conn.cursor() as cur:
            cur.execute("UPDATE g2p_list_version_values SET status='RETIRED' WHERE list_id='GENDER' AND value_code='MALE'")
        try:
            load_samples(connect, geo)
        except ValueError as error:
            assert "published GENDER" in str(error)
        else:
            raise AssertionError("Retired reference code accepted")
        print("PASS: 21 MDS people, 6 households; drafts/future versions ignored; retired code rejected")
    finally:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        conn.close()


if __name__ == "__main__":
    main()
