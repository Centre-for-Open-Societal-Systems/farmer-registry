"""Build the Farmer intake import template (an Excel workbook) from the register's schema.

The staff portal's native Import from file (OpenG2P registry design: bulk upload) takes any CSV or Excel file and
offers no template of its own. This workbook is that template, made from what the registry already declares:

- the columns are the ones the Jinja ingestion template reads (templates/farmer_file_import_intake.j2),
  in the order of import-templates/farmer_intake_import_template.csv;
- a dropdown column offers the codes of the Master Data list its staff-portal widget reads (attribute_id in the
  section metadata), taken from openg2p-data at the commit the db-seed image pins (docker/db-seed/Dockerfile);
- yes/no columns offer yes and no; dates, numbers and whole numbers are checked by Excel as they are typed;
  text that must keep its leading zeros (Fayda ID, phone numbers) is formatted as text.

Outputs, all committed: import-templates/farmer_intake_import_template.xlsx, the code-list block of the Jinja template and
import-templates/farmer_intake_code_lists.json (the code lists used, with the openg2p-data commit).

    python3 scripts/import_templates/build_import_template.py --pack <openg2p-data checkout>/packs/ETH-OAN
    python3 scripts/import_templates/build_import_template.py --from-snapshot     # rebuild from the committed lists

Validation in the workbook only helps whoever fills it in. The registry checks every row again on import: the Jinja
template refuses a value it cannot read (naming the column), and the intake's own rules and required fields run
when the intake is saved and finalized.
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "import-templates"
CSV = OUT / "farmer_intake_import_template.csv"
XLSX = OUT / "farmer_intake_import_template.xlsx"
SNAPSHOT = OUT / "farmer_intake_code_lists.json"
DOCKERFILE = REPO / "docker" / "db-seed" / "Dockerfile"
YES_NO = "YES_NO"
ROWS = 1000

# column: (maps to, required, kind, list, format). kind: text | code | yes_no | date | number | whole | ptext
COLUMNS = {
    "fayda_id": ("Identity", False, "ptext", None, "12-digit FIN or 16-digit FAN, digits only"),
    "first_name": ("Personal details", True, "text", None, "Text"),
    "middle_name": ("Personal details", False, "text", None, "Text"),
    "last_name": ("Personal details", True, "text", None, "Text"),
    "first_name_local": ("Personal details", False, "text", None, "Ge'ez script"),
    "middle_name_local": ("Personal details", False, "text", None, "Ge'ez script"),
    "last_name_local": ("Personal details", False, "text", None, "Ge'ez script"),
    "gender": ("Personal details", True, "code", "GENDER", "Code"),
    "birth_date": ("Personal details", False, "date", None, "YYYY-MM-DD"),
    "estimated_age": ("Personal details", False, "whole", None, "Whole number, when the birth date is not known"),
    "marital_status": ("Personal details", False, "code", "MARITAL_STATUS", "Code (required to submit)"),
    "language_spoken": ("Personal details", False, "code", "LANGUAGE", "Code"),
    "local_language": ("Personal details", False, "code", "LANGUAGE", "Code"),
    "farming_type": ("Personal details", False, "code", "FARMING_TYPE", "Code"),
    "email": ("Personal details", False, "text", None, "Email address"),
    "primary_phone_number": ("Phones", False, "ptext", None, "Ethiopian number; +251 or 251 is dropped"),
    "secondary_phone_number": ("Phones", False, "ptext", None, "Ethiopian number"),
    "education_level": ("Socio-economic", False, "code", "EDUCATION_LEVEL", "Code (required to submit)"),
    "source_of_income": ("Socio-economic", False, "code", "SOURCE_OF_INCOME", "Code"),
    "disabled": ("Socio-economic", False, "yes_no", YES_NO, "yes or no (required to submit)"),
    "disability_type": ("Socio-economic", False, "code", "DISABILITY_DOMAIN", "Code"),
    "disability_severity": ("Socio-economic", False, "code", "DISABILITY_SEVERITY", "Code"),
    "is_psnp_user": ("Socio-economic", False, "yes_no", YES_NO, "yes or no"),
    "is_household_head": ("Household", True, "yes_no", YES_NO, "yes or no"),
    "household_size": ("Household", False, "whole", None, "Whole number; default 1 (head only)"),
    "number_of_male_members": ("Household", False, "whole", None, "Whole number (head only)"),
    "number_of_female_members": ("Household", False, "whole", None, "Whole number (head only)"),
    "other_land_owner": ("Household", False, "yes_no", YES_NO, "yes or no; default no (head only)"),
    "region": ("Location", False, "ptext", None, "Master Data geo unit id (P-code), e.g. ET04"),
    "zone": ("Location", False, "ptext", None, "P-code, e.g. ET0404; needs the region"),
    "woreda": ("Location", False, "ptext", None, "P-code, e.g. ET040404; needs the zone"),
    "kebele": ("Location", False, "ptext", None, "P-code, e.g. ET04040404; needs the woreda"),
    "latitude": ("Location", False, "number", None, "Decimal degrees, -90 to 90; with longitude"),
    "longitude": ("Location", False, "number", None, "Decimal degrees, -180 to 180; with latitude"),
    "land_id": ("One land", False, "ptext", None, "Land certificate or parcel id"),
    "land_size": ("One land", False, "number", None, "Number (required to submit when a land is given)"),
    "land_unit": ("One land", False, "code", "LAND_SIZE_UNIT", "Code; default HECTARE"),
    "land_ownership_type": ("One land", False, "code", "LAND_OWNERSHIP_TYPE", "Code (required to submit when a land is given)"),
    "is_primary_cooperative_member": ("Membership", False, "yes_no", YES_NO, "yes or no (required to submit)"),
    "primary_cooperative_name": ("Membership", False, "text", None, "Text"),
    "is_cooperative_union_member": ("Membership", False, "yes_no", YES_NO, "yes or no (required to submit)"),
    "cooperative_union_name": ("Membership", False, "text", None, "Text"),
    "is_farmer_cluster_member": ("Membership", False, "yes_no", YES_NO, "yes or no (required to submit)"),
    "farmer_cluster_role": ("Membership", False, "code", "FARMER_CLUSTER_ROLE", "Code"),
    "primary_commodity": ("Membership", False, "code", "CROP_COMMODITY", "Code"),
    "identity_document_type": ("Documents", False, "code", "IDENTITY_DOCUMENT_TYPE", "Code; staff attach the file"),
    "enumerator_name": ("Identity", False, "text", None, "Who collected the data"),
    "enumerator_user_id": ("Identity", False, "ptext", None, "Their user id"),
    "data_collection_date": ("Identity", False, "date", None, "YYYY-MM-DD"),
}


def pinned_ref():
    match = re.search(r"^ARG OPENG2P_DATA_REF=([0-9a-f]{40})$", DOCKERFILE.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise SystemExit("docker/db-seed/Dockerfile has no ARG OPENG2P_DATA_REF=<40-hex commit>")
    return match.group(1)


def lists_from_pack(pack):
    """attribute_id -> [(code, label)] for the lists the columns use, from every JSON file of the pack."""
    wanted = {spec[3] for spec in COLUMNS.values() if spec[3] and spec[3] != YES_NO}
    found = {}
    for path in sorted(Path(pack).rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and data.get("attribute_id") in wanted and isinstance(data.get("values"), list):
            values = sorted(data["values"], key=lambda v: (v.get("sort_order") or 0, v.get("value_code") or ""))
            found[data["attribute_id"]] = [[v["value_code"], v.get("value_display") or v["value_code"]]
                                           for v in values if v.get("value_code") and v.get("is_active", True)]
    missing = sorted(wanted - set(found))
    if missing:
        raise SystemExit("not in the pack: " + ", ".join(missing))
    return dict(sorted(found.items()))


JINJA = REPO / "farmer-extension" / "src" / "openg2p_registry_farmer_extension" / "templates" / "farmer_file_import_intake.j2"
BLOCK = re.compile(r"(\{#- BEGIN code lists:.*?-#\}\n)(.*?)(\{#- END code lists -#\})", re.DOTALL)


def jinja_block(lists):
    """The two set statements of the Jinja template's generated block: list codes, and column -> list."""
    code_lists = {attribute: [code for code, _ in values] for attribute, values in lists.items()}
    code_columns = {column: spec[3] for column, spec in COLUMNS.items() if spec[2] == "code"}
    return (f"{{% set code_lists = {json.dumps(code_lists, ensure_ascii=False)} %}}\n"
            f"{{% set code_columns = {json.dumps(code_columns)} %}}\n")


def update_jinja(lists):
    text = JINJA.read_text(encoding="utf-8")
    if not BLOCK.search(text):
        raise SystemExit(f"{JINJA.name} has no generated code-list block")
    JINJA.write_text(BLOCK.sub(lambda m: m.group(1) + jinja_block(lists) + m.group(3), text), encoding="utf-8", newline="\n")


def build(lists, ref):
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    header = CSV.read_text(encoding="utf-8").strip().split(",")
    if header != list(COLUMNS):
        raise SystemExit("import-templates/farmer_intake_import_template.csv and COLUMNS differ")
    book = Workbook()
    sheet = book.active
    sheet.title = "Farmer intake"
    codes = book.create_sheet("Code lists")
    about = book.create_sheet("Columns")

    # Code lists: two columns per list (code, label); the dropdown reads the code column.
    ranges = {}
    for index, (attribute, values) in enumerate(lists.items()):
        code_col, label_col = get_column_letter(2 * index + 1), get_column_letter(2 * index + 2)
        codes[f"{code_col}1"], codes[f"{label_col}1"] = attribute, "label"
        codes[f"{code_col}1"].font = codes[f"{label_col}1"].font = Font(bold=True)
        for row, (code, label) in enumerate(values, start=2):
            codes[f"{code_col}{row}"], codes[f"{label_col}{row}"] = code, label
        ranges[attribute] = f"'Code lists'!${code_col}$2:${code_col}${len(values) + 1}"

    required_fill = PatternFill("solid", fgColor="FFF2CC")
    for index, (column, (maps_to, required, kind, attribute, fmt)) in enumerate(COLUMNS.items(), start=1):
        letter = get_column_letter(index)
        cell = sheet.cell(row=1, column=index, value=column)
        cell.font = Font(bold=True)
        if required:
            cell.fill = required_fill
        cell.comment = Comment(f"{maps_to}. {'Required. ' if required else ''}{fmt}", "OAN")
        sheet.column_dimensions[letter].width = max(14, len(column) + 2)
        area = f"{letter}2:{letter}{ROWS + 1}"
        rule = None
        if kind == "code":
            rule = DataValidation(type="list", formula1=ranges[attribute], allow_blank=True)
            rule.error = f"Pick a {attribute} code from the list (sheet Code lists)."
        elif kind == "yes_no":
            rule = DataValidation(type="list", formula1='"yes,no"', allow_blank=True)
            rule.error = "yes or no"
        elif kind == "date":
            rule = DataValidation(type="date", operator="between", formula1="DATE(1900,1,1)", formula2="DATE(2100,12,31)",
                                  allow_blank=True)
            rule.error = "A date (YYYY-MM-DD)"
            for row in range(2, ROWS + 2):
                sheet[f"{letter}{row}"].number_format = "yyyy-mm-dd"
        elif kind == "number":
            low, high = {"latitude": (-90, 90), "longitude": (-180, 180)}.get(column, (0, 1000000))
            rule = DataValidation(type="decimal", operator="between", formula1=str(low), formula2=str(high), allow_blank=True)
            rule.error = f"A number from {low} to {high}"
        elif kind == "whole":
            rule = DataValidation(type="whole", operator="between", formula1="0", formula2="200", allow_blank=True)
            rule.error = "A whole number"
        elif kind == "ptext":
            for row in range(2, ROWS + 2):
                sheet[f"{letter}{row}"].number_format = "@"
        if rule is not None:
            rule.errorTitle = column
            rule.showErrorMessage = True
            rule.add(area)
            sheet.add_data_validation(rule)
    sheet.freeze_panes = "A2"

    about.append(["column", "required", "maps to", "format", "code list"])
    for cell in about[1]:
        cell.font = Font(bold=True)
    for column, (maps_to, required, _kind, attribute, fmt) in COLUMNS.items():
        about.append([column, "yes" if required else "no", maps_to, fmt, attribute if attribute and attribute != YES_NO else ""])
    about.append([])
    about.append([(f"Code lists from openg2p-data {ref} (the commit docker/db-seed/Dockerfile pins). "
                  "Columns: docs/file-import.md. One row is one farmer; the registry checks every row again on import.")])
    for letter, width in zip("ABCDE", (30, 9, 18, 60, 24)):
        about.column_dimensions[letter].width = width
    book.properties.title = "Farmer intake import template"
    book.properties.creator = "OAN"
    return book


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pack", help="packs/ETH-OAN of an openg2p-data checkout at the pinned commit")
    source.add_argument("--from-snapshot", action="store_true", help="use import-templates/farmer_intake_code_lists.json")
    args = parser.parse_args(argv)
    ref = pinned_ref()
    if args.pack:
        lists = lists_from_pack(args.pack)
        SNAPSHOT.write_text(json.dumps({"openg2p_data_ref": ref, "lists": lists}, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
    else:
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        if snapshot["openg2p_data_ref"] != ref:
            raise SystemExit(f"snapshot is from {snapshot['openg2p_data_ref']}, the Dockerfile pins {ref}: rebuild with --pack")
        lists = snapshot["lists"]
    update_jinja(lists)
    book = build(lists, ref)
    book.save(XLSX)
    print(f"wrote {XLSX.relative_to(REPO)} ({len(COLUMNS)} columns, {len(lists)} code lists, openg2p-data {ref[:12]})")


if __name__ == "__main__":
    sys.exit(main())
