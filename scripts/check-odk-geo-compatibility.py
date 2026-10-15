#!/usr/bin/env python3
"""Read-only snapshot audit; no SQL execution, DB connections, or output files.

Usage: python scripts/check-odk-geo-compatibility.py --catalog catalog.json
       --references references.json
References contain only table, geo_lowest_level_value_id, and positive integer
count. An explicit [] means known-empty coverage; omission means unknown.
Exit 0 requires an exact catalog and known, already-exact references; 1 means
incompatible/unknown coverage, 2 means invalid input. Coverage is caller-asserted.
Labels use load_hierarchy's sibling-disambiguated labels. Legacy ET P-codes
are never padded, truncated, or inferred from labels or optional metadata.
"""

import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parent.parent
PARENTS = {"region": None, "zone": "region", "woreda": "zone", "kebele": "woreda"}
MAX_BYTES, MAX_ROWS = 32 * 1024 * 1024, 100_000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    require(isinstance(value, str) and 0 < len(value) <= 512
            and value.strip() == value, "Expected nonempty, unpadded text")
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def read_json(path):
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    require(len(data) <= MAX_BYTES, "Snapshot exceeds byte limit")
    return json.loads(data.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=lambda _: require(False, "Non-finite JSON number"))


def index_rows(rows, key, fields):
    require(isinstance(rows, list) and len(rows) <= MAX_ROWS, "Invalid row list")
    result = {}
    for row in rows:
        require(isinstance(row, dict) and fields <= row.keys(), "Missing required fields")
        identity = text(row[key])
        require(identity not in result, "Duplicate ID")
        for field in fields:
            if row[field] is not None or not field.startswith("parent_"):
                text(row[field])
        result[identity] = row
    return result


def validate_catalog(catalog):
    require(isinstance(catalog, dict) and set(catalog) == {"levels", "values"},
            "Expected levels and values")
    levels = index_rows(catalog["levels"], "level_id",
                        {"level_id", "level_mnemonic", "parent_level_id"})
    values = index_rows(catalog["values"], "level_value_id",
                        {"level_value_id", "level_id", "parent_level_value_id", "level_value_mnemonic"})
    require(0 < len(levels) <= 32, "Invalid level count")
    require(len({r["level_mnemonic"] for r in levels.values()}) == len(levels),
            "Duplicate level mnemonic")
    require(sum(r["parent_level_id"] is None for r in levels.values()) == 1, "Expected one root")
    for identity in levels:
        seen = set()
        while identity is not None:
            require(identity in levels and identity not in seen, "Dangling or cyclic level parent")
            seen.add(identity)
            identity = levels[identity]["parent_level_id"]
    for row in values.values():
        require(row["level_id"] in levels, "Unknown value level")
        parent = row["parent_level_value_id"]
        expected = levels[row["level_id"]]["parent_level_id"]
        require((parent is None and expected is None) or
                (parent in values and values[parent]["level_id"] == expected), "Invalid value parent")
    return levels, values


def canonical_catalog():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("odk_locations", REPO / "odk/build_location_media.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hierarchy = module.load_hierarchy(REPO / "local/upstream/assets/geo/ethiopia_geo_seed.sql.gz")
    levels, values = [], []
    for level, parent_level in PARENTS.items():
        levels.append({"level_id": "level-" + level, "level_mnemonic": level,
                       "parent_level_id": "level-" + parent_level if parent_level else None})
        for code, (label, parent) in hierarchy[level].items():
            values.append({"level_value_id": f"{level}-ET{code}", "level_id": "level-" + level,
                           "parent_level_value_id": f"{parent_level}-ET{parent}" if parent else None,
                           "level_value_mnemonic": label})
    return validate_catalog({"levels": levels, "values": values})


def reference_summary(references, expected_values):
    summary = {"coverage": "unknown" if references is None else "known", "tables": 0,
               "groups": 0, "records": 0, "already_exact": False}
    for category in ("exact_coss_ids", "legacy_et_pcode_candidates", "unmappable"):
        summary[category] = {"groups": 0, "records": 0}
    if references is None:
        return summary
    require(isinstance(references, list) and len(references) <= MAX_ROWS, "Invalid references list")
    # Only unchanged ET P-codes with an existing canonical target are candidates.
    legacy = {identity.split("-", 1)[1] for identity in expected_values}
    tables, seen = set(), set()
    for row in references:
        require(isinstance(row, dict) and set(row) ==
                {"table", "geo_lowest_level_value_id", "count"}, "Expected aggregate reference fields only")
        table, identity = text(row["table"]), text(row["geo_lowest_level_value_id"])
        count = row["count"]
        require(type(count) is int and 0 < count <= 2**63 - 1, "Invalid reference count")
        require((table, identity) not in seen, "Duplicate reference group")
        seen.add((table, identity))
        tables.add(table)
        category = ("exact_coss_ids" if identity in expected_values else
                    "legacy_et_pcode_candidates" if re.fullmatch(r"ET[0-9]+", identity)
                    and identity in legacy else "unmappable")
        summary[category]["groups"] += 1
        summary[category]["records"] += count
        summary["records"] += count
    summary.update(tables=len(tables), groups=len(seen), already_exact=
                   not (summary["legacy_et_pcode_candidates"]["groups"] or summary["unmappable"]["groups"]))
    return summary


def audit(catalog, references=None):
    levels, values = validate_catalog(catalog)
    wanted_levels, wanted_values = canonical_catalog()
    shape = {row["level_mnemonic"]: levels[row["parent_level_id"]]["level_mnemonic"]
             if row["parent_level_id"] else None for row in levels.values()}
    counts = dict.fromkeys(PARENTS, 0)
    expected_counts = dict.fromkeys(PARENTS, 0)
    for row in values.values():
        name = levels[row["level_id"]]["level_mnemonic"]
        counts[name] = counts.get(name, 0) + 1
    for row in wanted_values.values():
        expected_counts[wanted_levels[row["level_id"]]["level_mnemonic"]] += 1
    level_diff = {"missing_ids": len(wanted_levels.keys() - levels.keys()),
                  "extra_ids": len(levels.keys() - wanted_levels.keys()),
                  "mismatched": sum(any(levels[k][f] != wanted_levels[k][f]
                                        for f in ("level_mnemonic", "parent_level_id"))
                                    for k in levels.keys() & wanted_levels.keys())}
    value_diff = {"missing_ids": len(wanted_values.keys() - values.keys()),
                  "extra_ids": len(values.keys() - wanted_values.keys())}
    for field in ("level_id", "parent_level_value_id", "level_value_mnemonic"):
        value_diff[field + "_mismatches"] = sum(values[k][field] != wanted_values[k][field]
                                                 for k in values.keys() & wanted_values.keys())
    catalog_ok = shape == PARENTS and not any(level_diff.values()) and not any(value_diff.values())
    refs = reference_summary(references, wanted_values)
    return {"compatible": catalog_ok and refs["already_exact"],
            "catalog": {"compatible": catalog_ok, "level_shape_compatible": shape == PARENTS,
                        "counts_by_level": counts, "expected_coss_counts": expected_counts,
                        "levels": level_diff, "values": value_diff}, "references": refs}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--references", type=Path)
    args = parser.parse_args(argv)
    try:
        catalog = read_json(args.catalog)
        references = read_json(args.references) if args.references is not None else None
        require(args.references is None or isinstance(references, list), "Expected reference list")
        result = audit(catalog, references)
    except (OSError, ValueError, TypeError, KeyError, IndexError, UnicodeError, RecursionError):
        # Never echo parser exceptions, file contents, or reference identifiers.
        print(json.dumps({"compatible": False, "error": "Invalid snapshot or canonical hierarchy"}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["compatible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
