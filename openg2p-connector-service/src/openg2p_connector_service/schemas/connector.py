from datetime import datetime

from pydantic import BaseModel, model_validator


class ConnectorCreate(BaseModel):
    name: str
    platform: str
    transport_type: str
    enabled: bool = True
    paused: bool = False
    data_model_mnemonic: str | None = None
    mapper_expression: str | None = None
    mapper_version: str | None = None
    # G2P envelope — required for any data that must reach the registry
    g2p_sender_id: str
    g2p_register_mnemonic: str
    source_config_json: str | None = None
    auth_type: str = "none"
    auth_secret_json: str | None = None
    webhook_secret: str | None = None
    webhook_path_slug: str | None = None
    webhook_verifier: str = "hmac_sha256"
    poll_config_json: str | None = None
    max_in_flight: int | None = None
    validation_schema_json: str | None = None


class ConnectorUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    paused: bool | None = None
    data_model_mnemonic: str | None = None
    mapper_expression: str | None = None
    mapper_version: str | None = None
    g2p_sender_id: str | None = None
    g2p_register_mnemonic: str | None = None
    source_config_json: str | None = None
    auth_type: str | None = None
    auth_secret_json: str | None = None
    webhook_secret: str | None = None
    webhook_path_slug: str | None = None
    webhook_verifier: str | None = None
    poll_config_json: str | None = None
    max_in_flight: int | None = None
    validation_schema_json: str | None = None


class ConnectorRead(BaseModel):
    connector_id: str
    name: str
    platform: str
    transport_type: str
    enabled: bool
    paused: bool = False
    data_model_mnemonic: str | None = None
    mapper_expression: str | None = None
    mapper_version: str | None = None
    g2p_sender_id: str | None = None
    g2p_register_mnemonic: str | None = None
    source_config_json: str | None = None
    auth_type: str = "none"
    webhook_path_slug: str | None = None
    webhook_verifier: str = "hmac_sha256"
    poll_config_json: str | None = None
    max_in_flight: int | None = None
    validation_schema_json: str | None = None
    last_poll_at: datetime | None = None
    last_poll_status: str | None = None
    last_poll_error: str | None = None
    last_poll_fetched: int | None = None
    last_poll_duration_ms: int | None = None
    poll_state_json: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _mask_secrets(cls, data):
        """Never expose auth_secret_json or webhook_secret on read."""
        if hasattr(data, "__dict__"):
            return data
        data.pop("auth_secret_json", None)
        data.pop("webhook_secret", None)
        return data
