# OpenG2P Connector Service

Multi-transport integration gateway that ingests data from external platforms
(ODK Central, partner webhooks, Kafka topics, other registries) and feeds it
into the OpenG2P registry via `POST /partner/ingest_data` (Mode A).

## Quick start

```bash
# Install (core)
pip install -e .

# Install with Kafka consumer support
pip install -e ".[kafka]"

# Run API
python -m openg2p_connector_service.main

# Run Celery worker (for polling + async webhook processing)
celery -A openg2p_connector_service.worker worker --loglevel=info

# Run Celery beat (scheduled polls — dispatches every 60s, per-connector intervals gate execution)
celery -A openg2p_connector_service.worker beat --loglevel=info

# Run event consumer supervisor (Kafka / Rabbit / SQS)
python -m openg2p_connector_service.consumer_supervisor
# or: connector-consumer
```

Copy `.env.example` to `.env` and adjust values.

## Container deployment

For a production/deployment-oriented image, runtime roles, and env template,
see `DEPLOYMENT.md`.

## Architecture

```
External sources          Connector Service             Registry
─────────────────        ──────────────────────        ─────────
ODK Central ──poll──►    OdkCentralTransport
Partner API ──poll──►       │                          POST /partner/ingest_data
Webhook push ──────►    WebhookController ─► Worker ──►   │
Kafka topic  ──────►    ConsumerSupervisor              IngestionPipeline
                            │                            (classify → transform
                         IngestionService                 → change request)
                         (dedupe → map → send)
```

## Per-connector source configuration

Each connector stores its connection details in `source_config_json` (replaces
the old global `CONNECTOR_ODK_*` env vars):

### Webhook-only ODK

```json
{
  "name": "ODK Farm Survey (webhook)",
  "platform": "odk",
  "transport_type": "webhook",
  "webhook_path_slug": "odk-farm-survey",
  "webhook_verifier": "hmac_sha256",
  "webhook_secret": "<shared-secret>"
}
```

### ODK poll + session auth

```json
{
  "name": "ODK Household Poll",
  "platform": "odk",
  "transport_type": "odk_central",
  "auth_type": "odk_session",
  "source_config_json": "{\"base_url\":\"https://odk.example.com\",\"project_id\":1,\"form_id\":\"household\",\"poll_interval_seconds\":300}",
  "auth_secret_json": "{\"email\":\"admin@example.com\",\"password\":\"***\"}"
}
```

### ODK poll + OAuth2 (Keycloak token URL)

```json
{
  "name": "ODK via Keycloak",
  "platform": "odk",
  "transport_type": "odk_central",
  "auth_type": "oauth2_client_credentials",
  "source_config_json": "{\"base_url\":\"https://odk.example.com\",\"project_id\":2,\"form_id\":\"beneficiary\"}",
  "auth_secret_json": "{\"token_url\":\"https://keycloak.example.com/realms/odk/protocol/openid-connect/token\",\"client_id\":\"connector\",\"client_secret\":\"***\",\"scope\":\"openid\"}"
}
```

### Kafka event consumer

```json
{
  "name": "Partner Registry Events",
  "platform": "kafka_registry_events",
  "transport_type": "kafka_consumer",
  "auth_type": "none",
  "source_config_json": "{\"bootstrap_servers\":\"broker1:9092\",\"topic\":\"partner-events\",\"consumer_group\":\"connector-grp\",\"idempotency_key_path\":\"event_id\"}"
}
```

### WebSub push consumer

```json
{
  "name": "EDRMC WebSub",
  "platform": "edrmc_websub",
  "transport_type": "websub",
  "webhook_path_slug": "edrmc-websub",
  "webhook_verifier": "hmac_sha256",
  "webhook_secret": "<hub-secret>",
  "source_config_json": "{\"hub_url\":\"https://websub.example.org/hub\",\"partner_id\":\"openg2p-nsr-edrmc-consumer\",\"callback_url\":\"https://connector.example.org/webhook/by-slug/edrmc-websub\"}"
}
```

`websub` is a push transport: configure the WebSub hub to call the connector
webhook URL, and the connector will verify the hub signature, map the payload,
wrap it in the G2P envelope, and call the Registry Partner API.

### Generic partner webhook

```json
{
  "name": "Partner Push",
  "platform": "registry_partner",
  "transport_type": "webhook",
  "webhook_verifier": "plain_shared_token",
  "webhook_secret": "<token>"
}
```

## Auth strategies

| `auth_type` | Description | Secrets required |
|---|---|---|
| `none` | No auth headers | — |
| `static_bearer` | Fixed Bearer token | `token` |
| `odk_session` | ODK `POST /v1/sessions` | `email`, `password` |
| `oauth2_client_credentials` | Standard CC flow | `token_url`, `client_id`, `client_secret` |
| `oauth2_password` | ROPC flow | `token_url`, `client_id`, `username`, `password` |

## Webhook verification

| `webhook_verifier` | Header | Description |
|---|---|---|
| `hmac_sha256` (default) | `X-Hub-Signature-256: sha256=<hex>` | HMAC-SHA256 over raw body |
| `plain_shared_token` | `X-Webhook-Token: <token>` or `Authorization: Bearer <token>` | Simple token comparison |

Webhooks can be addressed by connector ID (`POST /webhook/{connector_id}`) or
by a human-readable slug (`POST /webhook/by-slug/{slug}`).

## Event consumers

Install the optional broker client:

```bash
pip install openg2p-connector-service[kafka]    # Kafka via aiokafka
pip install openg2p-connector-service[rabbit]   # RabbitMQ via aio-pika
pip install openg2p-connector-service[sqs]      # AWS SQS via aiobotocore
```

Run the supervisor:

```bash
connector-consumer   # or: python -m openg2p_connector_service.consumer_supervisor
```

Kafka auth (SASL) is configured via `auth_secret_json`:

```json
{
  "sasl_mechanism": "PLAIN",
  "username": "user",
  "password": "pass",
  "security_protocol": "SASL_SSL"
}
```

## Feature flags

| Env var | Default | Purpose |
|---|---|---|
| `CONNECTOR_OTEL_ENABLED` | `false` | Enable OpenTelemetry instrumentation |
| `CONNECTOR_VALIDATE_MAPPED_PAYLOAD` | `false` | Validate mapped payloads against `validation_schema_json` |
| `CONNECTOR_WEBHOOK_RATE_LIMIT_ENABLED` | `false` | Redis sliding-window rate limit per connector |

## Migration from global ODK env vars

The `CONNECTOR_ODK_CENTRAL_BASE_URL`, `CONNECTOR_ODK_CENTRAL_EMAIL`, and
`CONNECTOR_ODK_CENTRAL_PASSWORD` environment variables are deprecated. They
still work as fallbacks when `source_config_json` omits `base_url` / auth, but
will be removed in a future release. Move their values into per-connector API
calls or SQL seed data.
