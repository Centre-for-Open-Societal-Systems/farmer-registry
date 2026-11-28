"""The DCI search response is the farmer extension's template plus OAN's farmer_reference block."""

from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "farmer-extension/src/openg2p_registry_farmer_extension/templates"


def test_dci_search_response_is_the_farmer_template_with_the_reference_block_last():
    upstream = (TEMPLATES / "openg2p_farmer_to_dci.json.j2").read_text(encoding="utf-8").rstrip()
    response = (TEMPLATES / "farmer_dci_search_response.j2").read_text(encoding="utf-8")
    assert upstream.endswith("}")
    # Up to the farmer template's closing brace, the response is that template
    # unchanged; after an upstream template change, copy it in again above the block.
    head = upstream[:-1].rstrip() + "\n"
    assert response.startswith(head)
    block = response[len(head):]
    assert block.startswith("{#- The Farmer reference")
    assert '"farmer_reference": {' in block
    assert response.rstrip().endswith("}\n}")
