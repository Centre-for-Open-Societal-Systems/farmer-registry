"""Automatic seed of the default Farmer Registry ingestion pipeline.

Seeds one ODK Central pipeline on a fresh connector database, so a new
environment comes up with a working pipeline instead of an empty UI.

Everything environment-specific is read from the environment. There are no
fallback credentials and no fallback ODK host: an unconfigured deployment logs
what is missing and seeds nothing, rather than pointing at someone's sandbox.
Configure, at minimum:

    CONNECTOR_ODK_CENTRAL_BASE_URL   e.g. http://commons-services-odk-central-frontend
    CONNECTOR_ODK_PROJECT_ID         the ODK Central project holding the form
    CONNECTOR_ODK_FORM_ID            the published form's id
    CONNECTOR_ODK_CENTRAL_EMAIL      an ODK Central account with access
    CONNECTOR_ODK_CENTRAL_PASSWORD   its password (mount from a secret)

The pipeline is seeded with ON CONFLICT (name) DO NOTHING, so a pipeline that
has since been edited in the UI is never overwritten.
"""

import json
import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .config import get_settings

_logger = logging.getLogger("connector.pipelines.seed")

# One form, one pipeline. The connector_id is fixed so re-seeding is idempotent
# across environments.
DEFAULT_FARMER_PIPELINE = {
    "connector_id": "f17c6c2e5a7d4f0b9a1e3c8d4b6f2a10",
    "name": "Farmer Registry - ODK Central Ingestion",
}

# The registry classifies on these: far's semantic pattern matches a Farmer
# record, and master_data must hold a partner with this id.
PARTNER_ID = "farmer-partner"
REGISTER_MNEMONIC = "Farmer"
DATA_MODEL_MNEMONIC = "FARMER_ODK_MODEL"


def _setting(name: str, *fallback_env: str) -> str:
    """Read a setting from the connector settings or the environment."""
    value = getattr(get_settings(), name.lower(), "") or ""
    if not value:
        for env_name in fallback_env:
            value = os.environ.get(env_name) or ""
            if value:
                break
    return str(value).strip()


async def seed_default_pipelines(conn: AsyncConnection) -> None:
    """Ensure the standard Farmer pipeline exists in the connector database."""
    odk_base_url = _setting(
        "odk_central_base_url", "CONNECTOR_ODK_CENTRAL_BASE_URL", "ODK_CENTRAL_BASE_URL"
    ).rstrip("/")
    odk_project_id = _setting("odk_project_id", "CONNECTOR_ODK_PROJECT_ID", "ODK_PROJECT_ID")
    odk_form_id = _setting("odk_form_id", "CONNECTOR_ODK_FORM_ID", "ODK_FORM_ID")
    odk_email = _setting(
        "odk_central_email", "CONNECTOR_ODK_CENTRAL_EMAIL", "ODK_CENTRAL_EMAIL"
    )
    odk_password = _setting(
        "odk_central_password", "CONNECTOR_ODK_CENTRAL_PASSWORD", "ODK_CENTRAL_PASSWORD"
    )

    missing = [
        name
        for name, value in (
            ("CONNECTOR_ODK_CENTRAL_BASE_URL", odk_base_url),
            ("CONNECTOR_ODK_PROJECT_ID", odk_project_id),
            ("CONNECTOR_ODK_FORM_ID", odk_form_id),
            ("CONNECTOR_ODK_CENTRAL_EMAIL", odk_email),
            ("CONNECTOR_ODK_CENTRAL_PASSWORD", odk_password),
        )
        if not value
    ]
    if missing:
        _logger.info(
            "Not seeding the default pipeline: %s not set. Create the pipeline "
            "in the connector UI, or set these and restart.",
            ", ".join(missing),
        )
        return

    partner_base = (
        getattr(get_settings(), "partner_ingest_base_url", None)
        or os.environ.get("CONNECTOR_PARTNER_INGEST_BASE_URL")
        or ""
    ).strip().rstrip("/")
    if not partner_base:
        _logger.warning(
            "Not seeding the default pipeline: CONNECTOR_PARTNER_INGEST_BASE_URL is not set."
        )
        return

    source_config = {
        "base_url": odk_base_url,
        "project_id": int(odk_project_id),
        "form_id": odk_form_id,
        # Expands ODK repeat groups (land, crops, livestock) into the payload.
        "resolve_nav_links": True,
        "strict_incremental": False,
        "target_url": f"{partner_base}/partner/ingest_data",
        "target_headers": {
            "partner-id": PARTNER_ID,
            "Content-Type": "application/json",
        },
    }

    insert_stmt = text(
        """
        INSERT INTO connector_definitions (
            connector_id, name, platform, transport_type, enabled, paused,
            data_model_mnemonic, g2p_sender_id, g2p_register_mnemonic,
            source_config_json, auth_type, auth_secret_json, webhook_verifier
        ) VALUES (
            :connector_id, :name, 'odk_central', 'odk_central', true, false,
            :data_model_mnemonic, :sender_id, :register_mnemonic,
            :source_config_json, 'odk_session', :auth_secret_json, 'hmac_sha256'
        )
        ON CONFLICT (name) DO NOTHING;
        """
    )

    try:
        await conn.execute(
            insert_stmt,
            {
                "connector_id": DEFAULT_FARMER_PIPELINE["connector_id"],
                "name": DEFAULT_FARMER_PIPELINE["name"],
                "data_model_mnemonic": DATA_MODEL_MNEMONIC,
                "sender_id": PARTNER_ID,
                "register_mnemonic": REGISTER_MNEMONIC,
                "source_config_json": json.dumps(source_config),
                "auth_secret_json": json.dumps(
                    {"email": odk_email, "password": odk_password}
                ),
            },
        )
        _logger.info(
            "Auto-seeded connector pipeline %r for form %r",
            DEFAULT_FARMER_PIPELINE["name"],
            odk_form_id,
        )
    except Exception as exc:
        _logger.warning(
            "Could not auto-seed pipeline %s: %s", DEFAULT_FARMER_PIPELINE["name"], exc
        )
