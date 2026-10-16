#!/usr/bin/env python3
"""Explicit, offline-writer COSS migration; default dry-run always rolls back.

Runtime: Python 3.10+, psycopg2, PGHOST/PGPORT/PGUSER/PGPASSWORD. Supply both
database names and an existing backup directory. Apply requires --writers-stopped
and nonempty master-data.dump / registry.dump from fresh operator-run pg_dump.
Only backup paths/stat metadata are checked, not contents, freshness or provenance.
Two commits are NOT atomic. On error keep writers stopped and reconcile BOTH DBs
using recovery.json (old catalogs, exact geo text, old/new tuple keys) and dumps.
Never reuse tuple keys after writers resume or VACUUM FULL. No automatic recovery.
"""

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

REPO = Path(__file__).resolve().parent.parent
VERSION = "coss-ethiopia-four-levels-v1"
TABLES = ("g2p_geo_levels", "g2p_geo_level_values")
PARENTS = {"region": None, "zone": "region", "woreda": "zone", "kebele": "woreda"}
LOW, GEO = "geo_lowest_level_value_id", "geo_code_hierarchy_json"


class Refused(ValueError):
    """Only these curated messages may be printed; never raw driver/parser errors."""


def require(ok, message):
    if not ok:
        raise Refused(message)


def seed_catalog(text):
    """Parse only the checked-in seed's string/NULL INSERT literals, never SQL."""
    catalogs = {table: {} for table in TABLES}
    pattern = re.compile(r"INSERT INTO public\.(g2p_geo_levels|g2p_geo_level_values) \(([^)]+)\) VALUES \((.*)\) ON CONFLICT \((level_id|level_value_id)\) DO NOTHING;")
    token = re.compile(r"'(?:[^']|'')*'|NULL")
    for line in text.splitlines():
        if not any(line.startswith("INSERT INTO public." + table + " ") for table in TABLES):
            continue
        match = pattern.fullmatch(line)
        require(match, "Unsupported geography seed INSERT")
        table, columns, literals, conflict = match.groups()
        columns = [c.strip() for c in columns.split(',')]
        require(len(set(columns)) == len(columns) and all(re.fullmatch(r"[a-z_][a-z0-9_]*", c)
                for c in columns), "Invalid/duplicate seed columns")
        parsed, end = [], 0
        for value in token.finditer(literals):
            require(literals[end:value.start()].strip() == ("," if parsed else ""), "Unsupported geography seed value")
            literal = value.group()
            parsed.append(None if literal == "NULL" else literal[1:-1].replace("''", "'"))
            end = value.end()
        require(not literals[end:].strip() and len(parsed) == len(columns), "Incomplete geography seed row")
        row, key = dict(zip(columns, parsed)), "level_id" if table == TABLES[0] else "level_value_id"
        rows = catalogs[table]
        require(conflict == key and row.get(key) and row[key] not in rows, "Invalid/duplicate seed ID")
        require(not rows or row.keys() == next(iter(rows.values())).keys(), "Inconsistent seed columns")
        rows[row[key]] = row
    require(all(catalogs.values()), "Missing geography seed catalog")
    return tuple(catalogs[table] for table in TABLES)


def canonical():
    spec = importlib.util.spec_from_file_location("odk_locations", REPO / "odk/build_location_media.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = REPO / "local/upstream/assets/geo/ethiopia_geo_seed.sql.gz"
    seed = source.read_bytes()
    levels, values = seed_catalog(gzip.decompress(seed).decode("utf-8"))
    places = module.load_hierarchy(source)  # Parse literals only; never execute seed SQL.
    require(set(levels) == {"level-" + name for name in PARENTS} and len(values) == 21053,
            "Unexpected canonical catalog size/levels")
    for name, parent in PARENTS.items():
        identity = "level-" + name
        require(levels[identity]["level_mnemonic"] == name and levels[identity]["parent_level_id"] ==
                ("level-" + parent if parent else None), "Invalid canonical level chain")
        for code, (label, parent_code) in places[name].items():
            key = f"{name}-ET{code}"
            require(values[key]["level_id"] == identity and values[key]["parent_level_value_id"] ==
                    (f"{parent}-ET{parent_code}" if parent_code else None), "Invalid canonical place chain")
            values[key]["level_value_mnemonic"] = label  # Only override the selectable label.
    return levels, values, hashlib.sha256(seed).hexdigest()


def chain(identity, values):
    result, seen = [], set()
    while identity is not None:
        require(identity in values and identity not in seen, "Dangling/cyclic catalog parent")
        seen.add(identity)
        result.append(values[identity])
        identity = values[identity]["parent_level_value_id"]
    return list(reversed(result))


def mapping(old_levels, old_values, levels, values):
    require(len({v["level_mnemonic"] for v in old_levels.values()}) == len(old_levels), "Duplicate old level mnemonic")
    for key, level in old_levels.items():
        name, parent_id = level["level_mnemonic"], level["parent_level_id"]
        require(name in {"country", *PARENTS}, "Unknown old level mnemonic")
        parent_name = old_levels.get(parent_id, {}).get("level_mnemonic")
        require(parent_name == PARENTS.get(name) or name == "region" and parent_name == "country", "Invalid old level shape")
        seen, parent = {key}, level["parent_level_id"]
        while parent is not None:
            require(parent in old_levels and parent not in seen, "Invalid old level parent")
            seen.add(parent)
            parent = old_levels[parent]["parent_level_id"]
    result = {key: key for key in values}
    for key, row in old_values.items():
        require(row["level_value_id"] == key and isinstance(row["level_value_mnemonic"], str)
                and bool(row["level_value_mnemonic"]), "Invalid old place identity/label")
        require(row["level_id"] in old_levels, "Unknown old place level")
        ancestry = chain(key, old_values)
        parent = ancestry[-2]["level_id"] if len(ancestry) > 1 else None
        require(parent == old_levels[row["level_id"]]["parent_level_id"], "Invalid old place parent level")
        name = old_levels[row["level_id"]]["level_mnemonic"]
        target = name + "-" + key
        if re.fullmatch(r"ET[0-9]+", key) and target in values:
            result[key] = target
        if key in values:
            require(name == levels[values[key]["level_id"]]["level_mnemonic"], "Conflicting exact place level")
    # An unchanged code is not enough when a place moved to another parent in
    # the authoritative catalog. Exclude that alias and all its descendants;
    # preserve selected legacy values instead of guessing or blocking on unused
    # catalog differences. Exact COSS IDs with conflicting ancestry still fail.
    for key in sorted(old_values, key=lambda k: len(chain(k, old_values))):
        row = old_values[key]
        if key not in result:
            continue
        parent = row["parent_level_value_id"]
        expected = values[result[key]]["parent_level_value_id"]
        country = parent and old_levels[old_values[parent]["level_id"]]["level_mnemonic"] == "country"
        safe = ((parent is None and expected is None) or
                (country and expected is None and old_values[parent]["parent_level_value_id"] is None) or
                (not country and parent in result and result[parent] == expected))
        if not safe:
            require(key not in values, "Exact COSS place has conflicting old ancestry")
            del result[key]
    return result


def hierarchy(identity, levels, values):
    return dict(lowest_level_value_id=identity, hierarchy=[dict(
        level=levels[v["level_id"]]["level_mnemonic"], level_id=v["level_id"],
        level_mnemonic=levels[v["level_id"]]["level_mnemonic"],
        level_value_id=v["level_value_id"], level_value_mnemonic=v["level_value_mnemonic"])
        for v in chain(identity, values)])


def selection(lowest, raw, aliases, old_levels, old_values, levels, values):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, "Duplicate hierarchy JSON key")
            result[k] = v
        return result
    obj = json.loads(raw, object_pairs_hook=unique) if raw is not None else None
    require(obj is None or isinstance(obj, dict), "Hierarchy must be an object/null")
    obj = obj or {}
    json_id = obj.get("lowest_level_value_id")
    for identity in (lowest, json_id):
        require(identity is None or isinstance(identity, str) and bool(identity), "Invalid selection ID")
    require(not (lowest and json_id and lowest != json_id), "Conflicting column/JSON IDs")
    identity = lowest or json_id
    require(identity or not obj, "Nonempty hierarchy without selection")
    if not identity:
        return "empty", None
    if "hierarchy" in obj:
        rows = obj["hierarchy"]
        # Older registries stored only these three fields. The RC adds level
        # and level_id; validate them when present instead of rejecting valid
        # historical selections solely because those fields were not emitted.
        fields = ("level_mnemonic", "level_value_id", "level_value_mnemonic")
        require(isinstance(rows, list) and rows and all(isinstance(r, dict) and
                all(isinstance(r.get(k), str) and r[k] for k in fields) for r in rows)
                and rows[-1]["level_value_id"] == identity, "Malformed/conflicting hierarchy")
        require(len({r["level_value_id"] for r in rows}) == len(rows), "Repeated hierarchy place ID")
        if identity not in aliases:
            # Fictional legacy locations use district/ward/village. They cannot
            # be mapped, and their original JSON must remain untouched.
            return "unmapped", None
        for i, row in enumerate(rows):
            name, parent = row["level_mnemonic"], rows[i-1]["level_mnemonic"] if i else None
            require(row.get("level", name) == name and (name in {"country", *PARENTS}) and
                    (PARENTS.get(name) == parent or name == "region" and parent == "country"), "Malformed hierarchy level chain")
        options = [hierarchy(identity, n, c)["hierarchy"] for n, c in
                   ((old_levels, old_values), (levels, values)) if identity in c]
        require(not options or any(len(rows) == len(expected) and all(
                all(r.get(k) == e[k] for k in fields) and
                all(k not in r or r[k] == e[k] for k in ("level", "level_id"))
                for r, e in zip(rows, expected))
                for expected in options), "Stored hierarchy disagrees with catalog chain")
    if identity not in aliases:
        return "unmapped", None
    target = aliases[identity]
    updated = dict(obj, **hierarchy(target, levels, values))
    extras = {aliases.get(r["level_value_id"]): r for r in obj.get("hierarchy", [])}
    updated["hierarchy"] = [dict(extras.get(r["level_value_id"], {}), **r) for r in updated["hierarchy"]]
    return ("canonical" if lowest == target and obj == updated else "candidate"), (target, updated)


def journal_state(path, databases, digest):
    require(not path.is_symlink(), "Unsafe journal path")
    temporary = path.with_suffix(".tmp")
    require(not temporary.exists() and not temporary.is_symlink(), "Incomplete journal write; reconcile before proceeding")
    if not path.exists():
        return False
    require(not path.is_symlink() and path.is_file(), "Unsafe journal path")
    data = json.loads(path.read_text(encoding="utf-8"))
    require(data.get("state") == "complete", "Incomplete migration; keep writers stopped and reconcile both DBs")
    require((data.get("version"), data.get("sha256"), data.get("databases")) ==
            (VERSION, digest, databases), "Completed journal identity/checksum mismatch")
    return True


def backup_directory(path, apply):
    require(path.is_dir() and path.resolve() == Path(os.path.abspath(path)), "Unsafe/nonexistent journal directory")
    if apply:
        require(os.name == "posix", "Apply requires POSIX mode-600 journal permissions")
        for name in ("master-data.dump", "registry.dump"):
            backup = path / name
            require(not backup.is_symlink() and stat.S_ISREG(backup.stat().st_mode) and
                    backup.stat().st_size > 0 and backup.resolve().parent == path.resolve(), "Missing/unsafe backup file")


def persist(path, data, initial=False):
    temporary = path if initial else path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        if os.name == "posix":
            os.fchmod(stream.fileno(), 0o600)
        json.dump(data, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    if not initial:
        os.replace(temporary, path)
    if os.name == "posix":
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def ledger_check(applied, digest, complete, catalog_ok, changes):
    require(not applied or applied == digest, "Applied canonical checksum changed")
    require(not complete or applied, "Completed journal has no matching ledger")
    if applied:
        require(complete and catalog_ok and not changes, "Ledger/catalog/references inconsistent; reconcile manually")
    return bool(applied)


def catalog_matches(current, wanted):
    """Compare source fields projected onto actual schema columns; require core fields."""
    required = ({"level_id", "level_mnemonic", "parent_level_id"},
                {"level_value_id", "level_id", "level_value_mnemonic", "parent_level_value_id"})
    return len(current) == len(wanted) == 2 and all(set(actual) == set(expected) and all(
        fields <= row.keys() and all(row[k] == v for k, v in expected[key].items() if k in row)
        for key, row in actual.items()) for actual, expected, fields in zip(current, wanted, required))


def migrate(args):
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extras import Json, RealDictCursor, execute_values

    levels, values, digest = canonical()
    databases = [args.master_data_db, args.registry_db]
    path = args.journal_dir / "recovery.json"
    complete = journal_state(path, databases, digest)  # Before even opening DB transactions.
    connections = []
    q = lambda name: sql.Identifier("public", name)
    try:
        for database in databases:
            connections.append(psycopg2.connect(dbname=database, host=os.environ["PGHOST"],
                port=os.getenv("PGPORT", "5432"), user=os.environ["PGUSER"], password=os.environ["PGPASSWORD"]))
        m, r = [c.cursor(cursor_factory=RealDictCursor) for c in connections]
        for cursor, database in zip((m, r), databases):
            cursor.execute("SET LOCAL lock_timeout='10s'; SET LOCAL search_path=pg_catalog,public; SET LOCAL row_security=off")
            cursor.execute("SELECT current_database() AS db, pg_try_advisory_xact_lock(hashtext(%s)) AS locked", (VERSION,))
            row = cursor.fetchone()
            require(row["db"] == database and row["locked"], "Database identity mismatch/concurrent migration")
        m.execute("LOCK TABLE public.g2p_geo_levels, public.g2p_geo_level_values IN ACCESS EXCLUSIVE MODE")
        r.execute("""SELECT n.nspname AS schema, c.relname AS name, count(*) AS columns FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid
            WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema')
            AND a.attname IN (%s,%s) AND NOT a.attisdropped GROUP BY n.nspname,c.relname
            ORDER BY 1,2""", (LOW, GEO))
        tables = r.fetchall()
        require(tables and all(t.pop("columns") == 2 for t in tables), "Missing registry geography column pair")
        for table in tables:
            r.execute(sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(sql.Identifier(table["schema"], table["name"])))
        m.execute("SELECT to_regclass('public.coss_geo_migrations') AS ledger")
        applied = None
        if m.fetchone()["ledger"]:
            m.execute("SELECT sha256 FROM public.coss_geo_migrations WHERE version=%s", (VERSION,))
            row = m.fetchone()
            applied = row["sha256"] if row else None
        require(not applied or applied == digest, "Applied canonical checksum changed")
        def read_catalog():
            result = []
            for table, key in zip(TABLES, ("level_id", "level_value_id")):
                m.execute(sql.SQL("SELECT row_to_json(t) AS row FROM {} t").format(q(table)))
                rows = [v["row"] for v in m.fetchall()]
                result.append({v[key]: v for v in rows})
                require(len(rows) == len(result[-1]), "Duplicate catalog IDs")
            return result
        catalogs = read_catalog()
        old_levels, old_values = catalogs
        if applied:
            m.execute("SELECT catalog FROM public.coss_geo_catalog_archive WHERE version=%s", (VERSION,))
            archive = m.fetchone()
            require(archive, "Missing legacy catalog archive")
            old_levels, old_values = archive["catalog"]
        aliases = mapping(old_levels, old_values, levels, values)
        wanted = (levels, values)
        # Whole-record aggregate excluding ONLY the two allowed fields protects timestamps/other columns.
        fingerprint = sql.SQL("SELECT count(*) AS count, md5(string_agg(h,'' ORDER BY h)) AS hash FROM "
            "(SELECT md5((to_jsonb(t)-'geo_lowest_level_value_id'-'geo_code_hierarchy_json')::text) h FROM ONLY {} t) s")
        def survey():
            changes, fingerprints, counts = [], {}, dict.fromkeys(("empty", "unmapped", "canonical", "candidate"), 0)
            for table in tables:
                relation = sql.Identifier(table["schema"], table["name"])
                r.execute(fingerprint.format(relation))
                fingerprints[(table["schema"], table["name"])] = dict(r.fetchone())
                r.execute(sql.SQL("SELECT tableoid::oid AS tableoid, ctid::text AS ctid, {} AS lowest, {}::text AS raw FROM ONLY {}")
                          .format(sql.Identifier(LOW), sql.Identifier(GEO), relation))
                for row in r.fetchall():
                    category, update = selection(row["lowest"], row["raw"], aliases, old_levels, old_values, levels, values)
                    counts[category] += 1
                    if category == "candidate":
                        changes.append(dict(table, **row, target=update[0], updated=update[1]))
            return changes, fingerprints, counts
        changes, before, counts = survey()
        unchanged = ledger_check(applied, digest, complete, catalog_matches(catalogs, wanted), changes)
        print(json.dumps(dict(phase="before", levels=len(catalogs[0]), places=len(catalogs[1]),
            tables=len(tables), rows=sum(v["count"] for v in before.values()), **counts)), flush=True)
        if unchanged:
            print('Already complete; canonical catalog and references verified; no changes')
            return
        m.execute("""SELECT 1 FROM pg_constraint WHERE contype='f'
            AND confrelid IN ('public.g2p_geo_levels'::regclass,'public.g2p_geo_level_values'::regclass)
            AND conrelid NOT IN ('public.g2p_geo_levels'::regclass,'public.g2p_geo_level_values'::regclass) LIMIT 1""")
        require(not m.fetchone(), "Unexpected Master Data FK dependency; replacement refused")
        for cursor, relations in ((m, [q(t) for t in TABLES]), (r, [sql.Identifier(t["schema"], t["name"]) for t in tables])):
            for relation in relations:
                cursor.execute(sql.SQL("SELECT 1 FROM pg_trigger WHERE tgrelid={}::regclass AND NOT tgisinternal AND tgenabled<>'D' LIMIT 1")
                               .format(sql.Literal(relation.as_string(cursor))))
                require(not cursor.fetchone(), "Enabled user trigger could alter other columns; refused")
        for table, expected in zip(TABLES, wanted):
            m.execute(sql.SQL("CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP").format(sql.Identifier("new_" + table), q(table)))
            m.execute("SELECT column_name, column_default FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", (table,))
            schema = m.fetchall()
            require(not any("nextval(" in (v["column_default"] or "") for v in schema), "Sequence defaults cannot be rolled back; refused")
            columns = [v["column_name"] for v in schema if v["column_name"] in next(iter(expected.values()))]
            query = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(sql.Identifier("new_" + table), sql.SQL(',').join(map(sql.Identifier, columns)))
            execute_values(m, query, [tuple(row[c] for c in columns) for row in expected.values()])
        if not args.apply:
            print('Dry-run validated; rolling back both databases; no ledger/journal created')
            return
        journal = dict(state="prepared", version=VERSION, sha256=digest, databases=databases,
            catalogs=catalogs, records=changes, before=[dict(schema=k[0], name=k[1], **v) for k, v in before.items()])
        persist(path, journal, initial=True)
        m.execute("CREATE TABLE IF NOT EXISTS public.coss_geo_migrations (version text PRIMARY KEY, sha256 text NOT NULL)")
        m.execute("CREATE TABLE IF NOT EXISTS public.coss_geo_catalog_archive (version text PRIMARY KEY, catalog jsonb NOT NULL)")
        m.execute("INSERT INTO public.coss_geo_catalog_archive VALUES (%s,%s)", (VERSION, Json(catalogs)))
        for table in reversed(TABLES):
            m.execute(sql.SQL("DELETE FROM {}").format(q(table)))
        for table in TABLES:
            m.execute(sql.SQL("INSERT INTO {} SELECT * FROM {}").format(q(table), sql.Identifier("new_" + table)))
        for change in changes:
            r.execute(sql.SQL("UPDATE ONLY {} SET {}=%s,{}=%s WHERE tableoid=%s::oid AND ctid=%s::tid RETURNING ctid::text AS ctid")
                .format(sql.Identifier(change["schema"], change["name"]), sql.Identifier(LOW), sql.Identifier(GEO)),
                (change["target"], Json(change["updated"]), change["tableoid"], change["ctid"]))
            require(r.rowcount == 1, "Unexpected reference update count")
            change["new_ctid"] = r.fetchone()["ctid"]
        pending, after, after_counts = survey()
        require(not pending and after == before and after_counts["unmapped"] == counts["unmapped"] and
                after_counts["empty"] == counts["empty"], "Reference verification/count/non-geography checksum failed")
        require(catalog_matches(read_catalog(), wanted), "Installed catalog differs from canonical rows")
        m.execute("INSERT INTO public.coss_geo_migrations VALUES (%s,%s)", (VERSION, digest))
        journal["state"] = "committing"
        persist(path, journal)  # Includes post-update tuple keys; durable BEFORE either commit.
        connections[0].commit()
        connections[1].commit()
        journal["state"] = "complete"
        persist(path, journal)
        print(json.dumps(dict(phase="after", levels=4, places=21053, updated=len(changes),
            rows=sum(v["count"] for v in before.values()), unmapped_preserved=counts["unmapped"])), flush=True)
    finally:
        for connection in connections:
            try:
                connection.rollback()  # Only uncommitted work; cannot undo a completed commit.
            except psycopg2.Error:
                print('Connection cleanup failed; reconcile retained journal', file=sys.stderr)
            finally:
                connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master-data-db", required=True)
    parser.add_argument("--registry-db", required=True)
    parser.add_argument("--journal-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--writers-stopped", action="store_true")
    args = parser.parse_args(argv)
    try:
        require(args.master_data_db != args.registry_db and all(re.fullmatch(r"[A-Za-z0-9_-]+", n)
                for n in (args.master_data_db, args.registry_db)), "Explicit distinct database names required")
        require(not args.apply or args.writers_stopped, "Apply requires --writers-stopped acknowledgement")
        backup_directory(args.journal_dir, args.apply)
        migrate(args)
        return 0
    except Exception as error:
        # SQL/parser exceptions can contain private rows or connection credentials.
        message = str(error) if isinstance(error, Refused) else type(error).__name__
        print(f"Migration refused/failed: {message}. Keep writers stopped; inspect retained journal/backups.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
