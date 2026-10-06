import type { ConnectorCreate } from "../api/types"

/** Prod EDRMC hub → UD NSR connector (matches sandbox `edrmc-websub` pattern). */
export const EDRMC_WEBSUB_UD: ConnectorCreate = {
  name: "EDRMC NSR WebSub",
  platform: "edrmc_websub",
  transport_type: "websub",
  enabled: true,
  paused: false,
  data_model_mnemonic: "",
  mapper_expression:
    "groupData || individualData || group_data || individual_data || @",
  g2p_sender_id: "sr",
  g2p_register_mnemonic: "Individual",
  source_config_json: JSON.stringify(
    {
      hub_url: "https://websub.hrp.edrmc.gov.et/hub",
      partner_id: "openg2p-nsr-edrmc-consumer",
      callback_url:
        "https://connector-nsr.ud.mowsa.gov.et/webhook/by-slug/edrmc-websub",
    },
    null,
    2
  ),
  auth_type: "oauth2_client_credentials",
  auth_secret_json: JSON.stringify(
    {
      token_url:
        "https://keycloak.hrp.edrmc.gov.et/realms/master/protocol/openid-connect/token",
      client_id: "openg2p-nsr-edrmc-consumer",
      client_secret: "CHANGE_ME",
      scope: "openid",
    },
    null,
    2
  ),
  webhook_path_slug: "edrmc-websub",
  webhook_verifier: "hmac_sha256",
  webhook_secret: "websub",
  max_in_flight: null,
  validation_schema_json: "",
}
