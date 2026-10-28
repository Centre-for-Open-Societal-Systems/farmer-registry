"""Read country-pack samples from MDS; never invent or fall back to demo data.

MDS's published geography/list projections are used only for validation. The
sample tables are developer fixtures, not approved registry records. This seed
uses the same read-only MD_PG connection as the native registry seed.
"""
from datetime import date

import psycopg2.extras

CODED = {
    "gender": "GENDER", "relationship_to_head": "RELATIONSHIP_TO_HEAD",
    "marital_status": "MARITAL_STATUS", "education_level": "EDUCATION_LEVEL",
    "disability_status": "DISABILITY_STATUS",
}


def adapt_samples(people, households, geo_ids, codes):
    if not people or not households:
        raise ValueError("MDS samples are empty; load the selected country pack with samples enabled")
    by_id, by_household = {}, {}
    countries = {p.get("country") for p in people} | {h.get("country") for h in households}
    if len(countries) != 1 or not next(iter(countries)):
        raise ValueError("MDS samples must belong to exactly one country")
    for source in people:
        p = dict(source)
        ident = p["individual_id"]
        if ident in by_id:
            raise ValueError(f"Duplicate MDS individual {ident}")
        given, father = p.get("given_name"), p.get("fathers_name")
        prefix = f"{given} {father} "
        full = p.get("full_name") or ""
        if not given or not father or not full.startswith(prefix) or not full[len(prefix):].strip():
            raise ValueError(f"MDS sample {ident} needs a source-owned three-part full_name; reseed the updated country pack")
        if p.get("geo_pcode") not in geo_ids:
            raise ValueError(f"MDS sample {ident} has unpublished or missing geography")
        for field, code_list in CODED.items():
            if p.get(field) not in codes.get(code_list, set()):
                raise ValueError(f"MDS sample {ident}: {field} is not a published {code_list} code")
        if not p.get("national_id") or not p.get("birth_date"):
            raise ValueError(f"MDS sample {ident} requires national_id and birth_date")
        born = date.fromisoformat(str(p["birth_date"])[:10])
        today = date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if age < 0:
            raise ValueError(f"MDS sample {ident} has a future birth_date")
        p.update({
            "internal_record_id": ident, "first_name": given, "middle_name": father,
            "last_name": full[len(prefix):].strip(), "birth_date": born.isoformat(),
            "estimated_age": age, "foundational_id": str(p["national_id"]),
            "address_line_1": ", ".join(str(v) for v in (p.get("address_parts") or {}).values() if v),
            # Country remains the MDS ISO alpha-3 code; do not guess an alpha-2 code.
            "country_code": p["country"],
        })
        by_id[ident] = p
        by_household.setdefault(p["household_id"], []).append(p)
    if len({p["foundational_id"] for p in by_id.values()}) != len(by_id):
        raise ValueError("Duplicate national IDs in MDS sample people")
    out, seen = [], set()
    for source in households:
        h = dict(source)
        ident = h["household_id"]
        if ident in seen:
            raise ValueError(f"Duplicate MDS household {ident}")
        seen.add(ident)
        members = by_household.get(ident, [])
        head = by_id.get(h.get("head_individual_id"))
        if not head or head not in members:
            raise ValueError(f"MDS household {ident} has no valid head")
        if head["estimated_age"] < 18:
            raise ValueError(f"MDS household {ident} head cannot be seeded as an adult farmer")
        if h.get("geo_pcode") not in geo_ids:
            raise ValueError(f"MDS household {ident} has unpublished or missing geography")
        if h.get("size_total") != len(members):
            raise ValueError(f"MDS household {ident} size differs from its members")
        heads = [p for p in members if p["relationship_to_head"] in codes.get("HEAD_ROLES", set())]
        if len(heads) != 1 or heads[0] != head:
            raise ValueError(f"MDS household {ident} has inconsistent head relationships")
        h.update({"head": head, "members": members, "country_code": h["country"],
                  "address_line_1": ", ".join(str(v) for v in (h.get("address_parts") or {}).values() if v)})
        out.append(h)
    if set(by_household) != seen:
        raise ValueError("MDS contains sample people without a household")
    return list(by_id.values()), out


def load_samples(connect, geo_ids):
    conn = connect()
    if conn is None:
        raise ValueError("MD_PGHOST and MD_PGDATABASE are required")
    try:
        conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM g2p_sample_individuals ORDER BY individual_id")
            people = cur.fetchall()
            cur.execute("SELECT * FROM g2p_sample_households ORDER BY household_id")
            households = cur.fetchall()
            # Select the latest effective published version, not a draft or a
            # scheduled future version. Retired values cannot seed new records.
            cur.execute("""
                WITH current_lists AS (
                    SELECT DISTINCT ON (list_id) list_id, version_no, list_code
                    FROM g2p_list_versions WHERE status='PUBLISHED'
                      AND (effective_from IS NULL OR effective_from <= now())
                    ORDER BY list_id, version_no DESC
                )
                SELECT l.list_code,v.value_code,v.roles FROM current_lists l
                JOIN g2p_list_version_values v USING(list_id,version_no)
                WHERE v.status='ACTIVE'
            """)
            codes = {}
            for row in cur.fetchall():
                codes.setdefault(row["list_code"], set()).add(row["value_code"])
                if row["list_code"] == "RELATIONSHIP_TO_HEAD" and "head_of_household" in (row["roles"] or []):
                    codes.setdefault("HEAD_ROLES", set()).add(row["value_code"])
        return adapt_samples(people, households, geo_ids, codes)
    finally:
        conn.close()