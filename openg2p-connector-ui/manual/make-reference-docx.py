#!/usr/bin/env python3
"""Build docs/reference.docx with a bordered default Table style.

Pandoc's default Table style only puts a bottom border under the first row.
That makes our spec documents look borderless and visually sparse.

This script:
  1. Asks pandoc for its default reference.docx (`--print-default-data-file`).
  2. Patches word/styles.xml so the default Table style draws single 4-eighth-pt
     borders top/bottom/left/right and inside (horizontal + vertical), with a
     slightly stronger top border on the header row.
  3. Writes the patched archive back to docs/reference.docx.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Locate the pandoc binary that pypandoc shipped (used by export.sh too).
def find_pandoc() -> str:
    try:
        import pypandoc
        return pypandoc.get_pandoc_path()
    except Exception:
        return "pandoc"

def get_default_reference() -> bytes:
    pandoc = find_pandoc()
    proc = subprocess.run(
        [pandoc, "--print-default-data-file", "reference.docx"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return proc.stdout

# Replacement block for the Table style.
TABLE_STYLE = """<w:style w:type=\"table\" w:default=\"1\" w:styleId=\"Table\">
    <w:name w:val=\"Table\"/>
    <w:basedOn w:val=\"TableNormal\"/>
    <w:qFormat/>
    <w:tblPr>
      <w:tblInd w:w=\"0\" w:type=\"dxa\"/>
      <w:tblBorders>
        <w:top w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"595959\"/>
        <w:left w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"595959\"/>
        <w:bottom w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"595959\"/>
        <w:right w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"595959\"/>
        <w:insideH w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"BFBFBF\"/>
        <w:insideV w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"BFBFBF\"/>
      </w:tblBorders>
      <w:tblCellMar>
        <w:top w:w=\"60\" w:type=\"dxa\"/>
        <w:left w:w=\"108\" w:type=\"dxa\"/>
        <w:bottom w:w=\"60\" w:type=\"dxa\"/>
        <w:right w:w=\"108\" w:type=\"dxa\"/>
      </w:tblCellMar>
    </w:tblPr>
    <w:tblStylePr w:type=\"firstRow\">
      <w:rPr>
        <w:b/>
      </w:rPr>
      <w:tcPr>
        <w:shd w:val=\"clear\" w:color=\"auto\" w:fill=\"F2F2F2\"/>
        <w:tcBorders>
          <w:top w:val=\"single\" w:sz=\"6\" w:space=\"0\" w:color=\"595959\"/>
          <w:bottom w:val=\"single\" w:sz=\"6\" w:space=\"0\" w:color=\"595959\"/>
        </w:tcBorders>
      </w:tcPr>
    </w:tblStylePr>
  </w:style>"""


def patch_styles(xml: str) -> str:
    pattern = re.compile(
        r"<w:style[^>]*w:styleId=\"Table\"[^>]*>.*?</w:style>", re.S
    )
    new_xml, n = pattern.subn(TABLE_STYLE, xml, count=1)
    if n == 0:
        raise RuntimeError("Could not find Table style in styles.xml")
    return new_xml


def main() -> int:
    raw = get_default_reference()
    src = zipfile.ZipFile(io.BytesIO(raw), "r")
    out_path = HERE / "reference.docx"
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as dst:
        patched = False
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/styles.xml":
                xml = data.decode("utf-8")
                xml = patch_styles(xml)
                data = xml.encode("utf-8")
                patched = True
            dst.writestr(item, data)
        if not patched:
            raise RuntimeError("styles.xml not present in reference.docx")
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
