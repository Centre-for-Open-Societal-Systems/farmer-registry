export interface Connector {
  connector_id: string;
  name: string;
  platform: string;
  transport_type: string;
  enabled: boolean;
  paused: boolean;
  data_model_mnemonic: string | null;
  mapper_expression: string | null;
  mapper_version: string | null;
  g2p_sender_id: string | null;
  g2p_register_mnemonic: string | null;
  source_config_json: string | null;
  auth_type: string;
  webhook_path_slug: string | null;
  webhook_verifier: string;
  poll_config_json: string | null;
  max_in_flight: number | null;
  validation_schema_json: string | null;
  last_poll_at: string | null;
  last_poll_status: string | null;
  last_poll_error: string | null;
  last_poll_fetched: number | null;
  last_poll_duration_ms: number | null;
  poll_state_json?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConnectorStats {
  connector_id: string;
  is_active: boolean;
  last_poll_at: string | null;
  last_poll_status: string | null;
  last_poll_error: string | null;
  last_poll_fetched: number | null;
  last_poll_duration_ms: number | null;
  poll_interval_seconds: number | null;
  next_poll_at: string | null;
  dlq_count: number;
  run_status_counts: Record<string, number>;
  total_runs: number;
  poll_state: Record<string, unknown>;
  last_run: {
    run_id: string;
    status: string;
    source_event_id: string | null;
    registry_correlation_id: string | null;
    last_error: string | null;
    created_at: string;
    updated_at?: string;
  } | null;
}

export interface PollNowResponse {
  task_id: string;
  connector_id: string;
  queued_at: string;
}

/** Response from POST /connectors/{id}/websub/sync-subscriptions */
export interface WebSubTopicSyncResult {
  topic: string;
  register_http_status?: number;
  register_ok?: boolean;
  subscribe_http_status?: number;
  subscribe_ok?: boolean;
  register_body_preview?: string;
  subscribe_body_preview?: string;
  register_error?: string;
  subscribe_error?: string;
}

export interface WebSubSyncResponse {
  connector_id: string;
  hub_url: string;
  callback_url: string;
  topics_attempted: string[];
  all_subscribe_ok: boolean;
  results: WebSubTopicSyncResult[];
}

export interface ConnectorCreate {
  name: string;
  platform: string;
  transport_type: string;
  enabled?: boolean;
  paused?: boolean;
  data_model_mnemonic?: string | null;
  mapper_expression?: string | null;
  mapper_version?: string | null;
  // Required by the registry Partner API G2P envelope.
  g2p_sender_id: string;
  g2p_register_mnemonic: string;
  source_config_json?: string | null;
  auth_type?: string;
  auth_secret_json?: string | null;
  webhook_secret?: string | null;
  webhook_path_slug?: string | null;
  webhook_verifier?: string;
  poll_config_json?: string | null;
  max_in_flight?: number | null;
  validation_schema_json?: string | null;
}

export type ConnectorUpdate = Partial<ConnectorCreate>;

export interface ConnectorMeta {
  transport_types: string[];
  auth_types: string[];
  webhook_verifiers: string[];
  transport_hints: Record<string, string>;
}

export interface MetadataOption {
  value: string;
  label: string;
}

export interface MetadataList {
  configured: boolean;
  items: MetadataOption[];
  error?: string;
}

export interface IngestionRun {
  run_id: string;
  connector_id: string;
  source_event_id: string | null;
  correlation_id: string | null;
  status: string;
  attempt_count: number;
  last_error: string | null;
  registry_correlation_id: string | null;
  redelivery_count: number;
  connector_name: string | null;
  run_payload: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface RunsPage {
  items: IngestionRun[];
  total: number;
}

export interface DLQEntry {
  dl_id: string;
  connector_id: string;
  source_event_id: string | null;
  payload: Record<string, unknown> | null;
  error: string | null;
  error_category: string | null;
  attempt_count: number;
  connector_name: string | null;
  created_at: string;
}

export interface DLQPage {
  items: DLQEntry[];
  total: number;
}
