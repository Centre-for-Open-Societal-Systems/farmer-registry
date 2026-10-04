"""Shared defaults for API tests."""

G2P_DEFAULTS = {
    "g2p_sender_id": "test-partner",
    "g2p_register_mnemonic": "test_register",
}


def connector_json(**fields: object) -> dict:
    """POST /connectors body with required G2P envelope fields."""
    return {**G2P_DEFAULTS, **fields}
