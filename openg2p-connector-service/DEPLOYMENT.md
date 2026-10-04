# Connector Deployment

This directory now contains a container image definition for the Connector
Service that your DevOps team can deploy as one or more runtime roles from the
same image.

## Files

- `Dockerfile`: builds the Connector image
- `docker-entrypoint.sh`: selects the runtime role
- `deploy.env.example`: deployment-oriented env example

## Build

Build the base image:

```bash
docker build -t your-registry/openg2p-connector-service:latest ./openg2p-connector-service
```

Build with optional extras when needed:

```bash
docker build \
  --build-arg CONNECTOR_PIP_EXTRAS=metrics,kafka \
  -t your-registry/openg2p-connector-service:latest \
  ./openg2p-connector-service
```

Supported extras match `pyproject.toml`:

- `metrics`
- `kafka`
- `rabbit`
- `sqs`
- `otel`

## Runtime roles

The image defaults to `api`. Pass a different first argument to run another
role.

- `api`: FastAPI service on port `8050`
- `worker`: Celery worker for polling, webhook processing, and ingestion tasks
- `beat`: Celery beat scheduler for periodic `poll_all`
- `worker-beat`: single-container worker + beat for small environments
- `consumer`: event consumer supervisor for Kafka / RabbitMQ / SQS transports

## Recommended production topology

For polling and webhooks, run at least these three workloads:

1. `connector-api`
2. `connector-worker`
3. `connector-beat`

Only add `connector-consumer` if you use event-driven transports such as
Kafka, RabbitMQ, or SQS.

For very small deployments you can replace `worker` + `beat` with a single
`worker-beat` container, but separate workloads are better for scaling and
restarts.

## Required infrastructure

The connector expects these external services:

- PostgreSQL for the connector's own metadata and run tables
- Redis for Celery broker/result backend
- OpenG2P Registry Partner API

Optional integrations:

- Master data DB and registry DB DSNs for UI dropdown metadata
- Kafka, RabbitMQ, or AWS SQS when event transports are enabled

## Required environment variables

Use `deploy.env.example` as the starting point.

The minimum required values in most deployments are:

```env
CONNECTOR_DB_DRIVER=postgresql+asyncpg
CONNECTOR_DB_HOSTNAME=postgres
CONNECTOR_DB_PORT=5432
CONNECTOR_DB_USERNAME=connector
CONNECTOR_DB_PASSWORD=change-me
CONNECTOR_DB_DBNAME=connector

CONNECTOR_PARTNER_INGEST_BASE_URL=http://registry-partner-api:8002

CONNECTOR_CELERY_BROKER_URL=redis://redis:6379/1
CONNECTOR_CELERY_RESULT_BACKEND=redis://redis:6379/1
```

Important note:

- `CONNECTOR_PARTNER_INGEST_BASE_URL` must be the Partner API base URL only.
  Do not append `/partner/ingest_data`; the connector appends that path itself.

Recommended production defaults:

```env
CONNECTOR_LOG_LEVEL=INFO
CONNECTOR_STORE_RUN_PAYLOADS=false
CONNECTOR_STRICT_INCREMENTAL=true
CONNECTOR_FULL_SCAN_ON_INCREMENTAL_UNSUPPORTED=false
```

## Docker run examples

API:

```bash
docker run -d \
  --name connector-api \
  --env-file deploy.env \
  -p 8050:8050 \
  your-registry/openg2p-connector-service:latest
```

Worker:

```bash
docker run -d \
  --name connector-worker \
  --env-file deploy.env \
  your-registry/openg2p-connector-service:latest \
  worker
```

Beat:

```bash
docker run -d \
  --name connector-beat \
  --env-file deploy.env \
  your-registry/openg2p-connector-service:latest \
  beat
```

Event consumer:

```bash
docker run -d \
  --name connector-consumer \
  --env-file deploy.env \
  your-registry/openg2p-connector-service:latest \
  consumer
```

## Kubernetes / platform mapping

Map the same image to separate workloads:

- Deployment `connector-api` with container args omitted or `["api"]`
- Deployment `connector-worker` with args `["worker"]`
- Deployment `connector-beat` with args `["beat"]`
- Deployment `connector-consumer` with args `["consumer"]` when needed

Expose only the API workload via a Service.

## Health checks

For the API container:

- liveness: `GET /health`
- readiness: `GET /health/ready`

Suggested probe target:

```text
http://<pod-or-service>:8050/health/ready
```

Worker, beat, and consumer roles do not expose HTTP endpoints. Treat them as
background workers and monitor process health plus logs / queue depth.

## Startup behavior

On API and worker startup, the connector automatically:

- creates missing connector tables
- applies the lightweight in-process DB migrations in `db_migrations.py`

No separate migration job is required for the current implementation.

## Notes for ODK polling

Per-connector ODK settings belong in connector records stored in the connector
database, usually in:

- `source_config_json`
- `auth_secret_json`

The deprecated global `CONNECTOR_ODK_CENTRAL_*` env vars are still supported as
fallbacks, but new deployments should leave them blank and use per-connector
configuration instead.
