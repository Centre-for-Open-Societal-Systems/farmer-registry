"""Guard: search_text is built from real columns.

The register list and the DCI search match search_text (ILIKE), so a record is only findable by what its search_text
holds. Core fills it on save from each register's domain service (construct_search_text, reached through the
model's get_search_text_fields); OAN's Farmer and Farmer intake classes build it from FARMER_SEARCH_FIELDS
(register_domain/derived.py). A field name that is not a column reads as None, and the record silently stops being
findable by it.
"""

import ast
import re
from pathlib import Path

from test_metadata_consistency import columns, models

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "farmer-extension/src/openg2p_registry_farmer_extension"
NATIVE_SERVICES = EXT / "openg2p_farmer/register_domain/services"

# register_domain/services/__init__.py registers FarmerPhoneService under the FarmerPhone register's name.
OAN_SERVICES = {"FarmerPhone": (EXT / "register_domain/services/farmer_phone.py", "FarmerPhoneService")}


def search_text_reads():
    """{register mnemonic: field names its construct_search_text reads}."""
    services = {path: None for path in sorted(NATIVE_SERVICES.glob("g2p_register_domain_service_*.py"))}
    services.update({path: (mnemonic, name) for mnemonic, (path, name) in OAN_SERVICES.items()})
    reads = {}
    for path, oan in services.items():
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ClassDef):
                continue
            if oan:
                if node.name != oan[1]:
                    continue
                mnemonic = oan[0]
            else:
                mnemonic = node.name.removeprefix("G2PRegisterDomainService")
            for function in node.body:
                if isinstance(function, ast.FunctionDef) and function.name == "construct_search_text":
                    fields = set()
                    for n in ast.walk(function):
                        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "get" and n.args \
                                and isinstance(n.args[0], ast.Constant):
                            fields.add(n.args[0].value)
                        elif isinstance(n, (ast.List, ast.Tuple)):
                            fields |= {e.value for e in n.elts
                                       if isinstance(e, ast.Constant) and isinstance(e.value, str)}
                    reads[mnemonic] = fields
    tree = ast.parse((EXT / "register_domain/derived.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "FARMER_SEARCH_FIELDS":
            reads["Farmer"] = reads.get("Farmer", set()) | {e.value for e in node.value.elts}
    return reads


def test_search_text_reads_model_columns():
    reads = search_text_reads()
    registers = set(models()[0])
    # Every register builds a search_text; PovertyScore's service is for core's Score register.
    assert registers <= set(reads), registers - set(reads)
    assert {"functional_record_id", "first_name_local", "rid"} <= reads["Farmer"]
    missing = {mnemonic: sorted(fields - columns(mnemonic)) for mnemonic, fields in reads.items()
               if mnemonic in registers and fields - columns(mnemonic)}
    assert not missing, missing


def test_raw_register_inserts_write_search_text():
    """Raw SQL does not fire the ORM listeners that fill search_text, so a row inserted that way must write it.

    test/sanity/sanity/data_seed.py does (its docstring explains why); any later loader must too. A Python file
    builds its column list apart from the INSERT, so the check is that the file names search_text.
    """
    tables = "|".join(sorted(models()[1]))
    insert = re.compile(rf"INSERT\s+INTO\s+(?:\"?public\"?\.)?\"?(?:{tables})\b", re.I)
    writers = []
    skip = {".git", "node_modules", ".venv", "venv", "__pycache__"}
    for path in sorted(p for p in ROOT.rglob("*") if p.suffix in (".py", ".sql", ".sh") and not skip & set(p.parts)
                       and p.relative_to(ROOT).parts[:2] != ("test", "unit")):
        text = path.read_text(errors="ignore")
        if insert.search(text):
            writers.append((path.relative_to(ROOT).as_posix(), "search_text" in text))
    assert ("test/sanity/sanity/data_seed.py", True) in writers
    assert all(names for _, names in writers), [name for name, names in writers if not names]
