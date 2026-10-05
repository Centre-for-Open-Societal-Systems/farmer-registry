#!/usr/bin/env python3
"""Post-process pandoc-generated .docx files for Google Docs compatibility.

Google Docs ignores ``<w:tblBorders>`` declared on a *style* (the way pandoc's
reference docx does it). To make tables render with visible borders in Google
Docs (and Word, LibreOffice, Pages, …) the borders must be applied directly to
each ``<w:tbl>`` and ``<w:tc>`` element.

This script walks the document XML and:

* Removes the style-level ``<w:tblBorders>`` reliance by injecting an inline
  ``<w:tblBorders>`` block into every ``<w:tblPr>``.
* Injects ``<w:tcBorders>`` into every ``<w:tcPr>`` so that even merged or
  oddly-shaped cells still draw their borders in Google Docs.
* Forces a sensible default cell margin so text doesn't touch the grid lines.

The script is idempotent — running it again on an already-processed file is a
no-op for borders that already exist.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"

TBL_BORDERS = (
    "<w:tblBorders>"
    '<w:top w:val="single" w:sz="6" w:space="0" w:color="595959"/>'
    '<w:left w:val="single" w:sz="6" w:space="0" w:color="595959"/>'
    '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="595959"/>'
    '<w:right w:val="single" w:sz="6" w:space="0" w:color="595959"/>'
    '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
    '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
    "</w:tblBorders>"
)

TC_BORDERS = (
    "<w:tcBorders>"
    '<w:top w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
    '<w:left w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
    '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
    '<w:right w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
    "</w:tcBorders>"
)

CELL_MARGIN = (
    "<w:tcMar>"
    '<w:top w:w="60" w:type="dxa"/>'
    '<w:left w:w="108" w:type="dxa"/>'
    '<w:bottom w:w="60" w:type="dxa"/>'
    '<w:right w:w="108" w:type="dxa"/>'
    "</w:tcMar>"
)


def inject_after_open_tag(xml: str, parent_tag: str, addition: str,
                          skip_if_contains: str) -> str:
    """Insert ``addition`` immediately after each ``<parent_tag>`` open tag
    (self-closing or with content), unless ``skip_if_contains`` already exists
    inside that parent element.
    """
    pattern = re.compile(
        rf"<w:{parent_tag}(\s[^/>]*)?(/?)>", re.S
    )
    out = []
    last = 0
    for m in pattern.finditer(xml):
        out.append(xml[last:m.start()])
        attrs = m.group(1) or ""
        self_closing = m.group(2) == "/"
        if self_closing:
            out.append(f"<w:{parent_tag}{attrs}>{addition}</w:{parent_tag}>")
            last = m.end()
            continue
        end_match = re.search(rf"</w:{parent_tag}>", xml[m.end():])
        if not end_match:
            out.append(xml[m.start():m.end()])
            last = m.end()
            continue
        body = xml[m.end():m.end() + end_match.start()]
        new_body = body if skip_if_contains in body else addition + body
        out.append(f"<w:{parent_tag}{attrs}>{new_body}</w:{parent_tag}>")
        last = m.end() + end_match.end()
    out.append(xml[last:])
    return "".join(out)


def process_document_xml(xml: str) -> str:
    xml = inject_after_open_tag(xml, "tblPr", TBL_BORDERS, "<w:tblBorders")
    xml = inject_after_open_tag(xml, "tcPr", TC_BORDERS, "<w:tcBorders")
    xml = inject_after_open_tag(xml, "tcPr", CELL_MARGIN, "<w:tcMar")
    return xml


def process_docx(path: Path) -> None:
    raw = path.read_bytes()
    with zipfile.ZipFile(path, "r") as src:
        names = src.namelist()
        files = {name: src.read(name) for name in names}
        infos = {name: src.getinfo(name) for name in names}

    target = "word/document.xml"
    if target not in files:
        raise RuntimeError(f"{path} has no {target}")
    original_xml = files[target].decode("utf-8")
    new_xml = process_document_xml(original_xml)
    files[target] = new_xml.encode("utf-8")

    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in names:
            info = infos[name]
            new_info = zipfile.ZipInfo(filename=info.filename,
                                       date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            new_info.create_system = info.create_system
            dst.writestr(new_info, files[name])
    tmp.replace(path)
    print(f"  processed {path.name} ({path.stat().st_size} bytes)")


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: postprocess-docx.py FILE.docx [FILE.docx ...]",
              file=sys.stderr)
        return 1
    for p in argv:
        process_docx(Path(p))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
