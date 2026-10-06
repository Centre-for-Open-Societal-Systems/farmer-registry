# OpenG2P Connector Admin UI

Standalone admin interface for managing OpenG2P integration pipelines (connector definitions). Talks directly to the [openg2p-connector-service](../openg2p-connector-service/) REST API.

## Quick start

```bash
# Terminal 1 — Connector API (default port 8050)
cd ../openg2p-connector-service
cp .env.example .env   # once
python -m openg2p_connector_service.main

# Terminal 2 — UI
npm install
npm run dev
```

Open the Vite URL (usually http://localhost:5173). The UI calls `/connectors`, `/runs`, etc. on the same origin; Vite proxies those paths to `http://127.0.0.1:8050`.

## Environment

Copy `.env.example` to `.env`. **Recommended for local dev:** leave `VITE_CONNECTOR_API_BASE_URL` empty so the Vite proxy handles API calls (no CORS).

**Optional — browser calls the API directly:**

```
VITE_CONNECTOR_API_BASE_URL=http://localhost:8050
```

Then enable CORS on the connector service:

```bash
# In openg2p-connector-service/.env:
CONNECTOR_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Point the dev proxy at a remote API (e.g. UD) without changing the UI env:

```bash
VITE_DEV_CONNECTOR_PROXY_TARGET=https://connector-nsr.ud.mowsa.gov.et npm run dev
```

## Features

- **Pipeline list** — view all connectors with status, transport type, auth, last poll time.
- **Create / edit pipeline** — multi-section form with meta-driven dropdowns for transport types, auth strategies, and webhook verifiers.
- **Source configuration** — JSON textarea for `source_config_json` (base_url, poll_interval, ODK project/form, Kafka topic, etc.).
- **Auth secrets** — write-only password fields; secrets are never read back from the API.
- **Mapping** — JMESPath expression editor.
- **Webhook config** — slug, verifier selection, shared secret.
- **Runs** — read-only table of recent ingestion runs.
- **Dead Letter Queue** — view failed entries with error category; one-click replay.

## Auth (MVP)

The current version has **no login flow**. This is acceptable when:

- The connector service is on an internal network (not internet-facing).
- Access is controlled at the network layer (VPN, Kubernetes NetworkPolicy, Istio AuthorizationPolicy).

**Phase 2 (follow-up):** Add OIDC login (e.g. Keycloak) and pass JWT to a backend that validates it. Or add `CONNECTOR_ADMIN_API_KEY` to the connector service and send it via `X-API-Key` header from the SPA (only safe for internal tools; never commit keys).

## Tech stack

- React + TypeScript
- Tailwind CSS (v4)
- Vite
- React Router
- Lucide icons
