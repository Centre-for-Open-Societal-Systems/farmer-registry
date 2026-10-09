-- ==============================================================================
-- OpenG2P Connector Service — Pipeline Definitions Seed
-- Connects ODK Central (Form: farmer_profile) to Farmer Registry Partner API
-- Target DB: connector
--
-- Replace <odk-account-email> / <odk-account-password> with an ODK Central
-- account that can read the project's submissions before running this; no
-- login is committed. (Or create the pipeline in the connector UI.)
-- ==============================================================================

INSERT INTO connector_definitions (
    connector_id,
    name,
    platform,
    transport_type,
    enabled,
    paused,
    data_model_mnemonic,
    g2p_sender_id,
    g2p_register_mnemonic,
    source_config_json,
    auth_type,
    auth_secret_json,
    webhook_verifier
) VALUES (
    'farmer-odk-pipeline-01',
    'Farmer Registry - ODK Central Ingestion',
    'odk_central',
    'odk_central',
    true,
    false,
    'FARMER_ODK_MODEL',
    'farmer-partner',
    'Farmer',
    '{
        "base_url": "https://odk.13.207.43.8.nip.io",
        "project_id": 13,
        "form_id": "farmer_profile",
        "resolve_nav_links": true,
        "strict_incremental": false,
        "target_url": "http://farmer-registry-partner-api:8000/partner/ingest_data",
        "target_headers": {
            "partner-id": "farmer-partner",
            "Content-Type": "application/json"
        }
    }',
    'odk_session',
    '{
        "email": "<odk-account-email>",
        "password": "<odk-account-password>"
    }',
    'hmac_sha256'
)
ON CONFLICT (connector_id) DO UPDATE SET
    name = EXCLUDED.name,
    data_model_mnemonic = EXCLUDED.data_model_mnemonic,
    g2p_sender_id = EXCLUDED.g2p_sender_id,
    g2p_register_mnemonic = EXCLUDED.g2p_register_mnemonic,
    source_config_json = EXCLUDED.source_config_json,
    auth_type = EXCLUDED.auth_type,
    auth_secret_json = EXCLUDED.auth_secret_json,
    enabled = EXCLUDED.enabled,
    paused = EXCLUDED.paused;
