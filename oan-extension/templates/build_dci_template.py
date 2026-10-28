#!/usr/bin/env python3
"""Write OAN's Farmer DCI search response template: the farmer extension's own
template, unchanged, with the Farmer reference block (farmer_reference_block.j2)
added as its last top-level object.

Run at image build, so the template follows the farmer extension's on every
upgrade:

    build_dci_template.py <upstream.j2> farmer_reference_block.j2 farmer_dci_search_response.j2
"""

import sys
from pathlib import Path


def build(upstream: str, fragment: str) -> str:
    body = upstream.rstrip()
    if not body.endswith("}"):
        raise SystemExit("The farmer extension's DCI template no longer ends with its JSON object's closing brace")
    return body[:-1].rstrip() + "\n" + fragment.strip() + "\n"


if __name__ == "__main__":
    upstream, fragment, out = (Path(p) for p in sys.argv[1:4])
    out.write_text(build(upstream.read_text(encoding="utf-8"), fragment.read_text(encoding="utf-8")), encoding="utf-8")
