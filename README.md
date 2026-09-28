# Farmer Registry

An installable **Farmer Registry** built as a thin extension of the OpenG2P
[registry platform](https://github.com/OpenG2P/registry-platform). Under the
inverted build model the platform publishes the runnable base images and the
`openg2p-registry` Helm chart; this repo adds **only** the farmer domain on top.

---

## What this repo owns

| Path | Purpose |
|---|---|
| `farmer-extension/` | The farmer domain package — models, schemas, services, seed metadata (registers, AWE policy, DCI templates) |
| `docker/` | Thin Dockerfiles (`FROM openg2p/openg2p-registry-*` + `pip install farmer-extension`) selected at runtime by `REGISTRY_EXTENSION_MODULE` (Option C) |
| `helm/openg2p-farmer-registry/` | A thin wrapper chart: pins `openg2p-registry` as a dependency and supplies the farmer values overlay (no templates) |
| `test/sanity/` | The farmer **field-specific** sanity tests (Set 2); the harness + generic tests are inherited from the platform sanity image |
| `odk/` | ODK field profiling assets: official XLSForm v2, Kebele/Cooperative lookup datasets, Jinja2 transformation templates, and sync scripts |

The `openg2p-registry` base image tag (`RP_VERSION` in each Dockerfile) and the
chart dependency version in `helm/openg2p-farmer-registry/Chart.yaml` are **hardcoded and
pinned together**. The farmer images and the wrapper chart are versioned in
lockstep by CI (one version per commit).

To see which version it would pick, run `./scripts/bump-rp-version.sh -n` (dry-run,
writes nothing); `-h` prints help. To apply, run `./scripts/bump-rp-version.sh`
(latest published version) or `./scripts/bump-rp-version.sh <version>` — it updates
the Dockerfiles and the chart dependency together, so they can never drift. A CI
check (`test/test_rp_pin_lockstep.py`) fails the build if they ever do.

---

## DevOps & Deployment Guide

This section provides complete operational instructions for both **Local Development** and **Production Kubernetes** environments.

### 1. System Architecture & Components

The Farmer Registry runs as a coordinated stack of microservices:

| Component | Container Port | Host Port (Local) | Purpose |
| :--- | :--- | :--- | :--- |
| **`staff-ui`** | `3000` | `3001` | Web Portal for registry officers to review intake, approve registrations, and search records. |
| **`staff-api`** | `8000` | `8001` | Core FastAPI backend with `farmer-extension` domain logic, deduplication, and ODK webhooks. |
| **`partner-api`** | `8000` | `8006` | Ingestion gateway accepting external partner payloads (`POST /partner/ingest_data`). |
| **`celery-worker`** | N/A | N/A | Asynchronous processing engine for classification, Jinja2 rendering, and bulk intake creation. |
| **`celery-beat`** | N/A | N/A | Periodic scheduler for background tasks and maintenance jobs. |
| **`master-data-api`** | `8000` | `8042` | Manages partners (`g2p_partners`), API keys, and partner authorization. |
| **`postgres`** | `5432` | `5445` | Primary relational database (`farmer_registry_db` and `master_data`). |
| **`redis`** | `6379` | `6387` | Message broker and caching layer for Celery. |
| **`minio`** | `9000` / `9001` | `9002` / `9001` | S3-compatible object store for documents, photos, and Jinja2 templates (`templates`). |
| **`keycloak`** | `8080` | `8080` | IAM and OAuth2 / OpenID Connect authentication provider for staff and APIs. |

---

### 2. Local & Staging Deployment (Docker Compose)

#### Prerequisites
* Docker Engine 24.0+ & Docker Compose v2+
* Minimum 8 GB RAM (16 GB recommended for full local stack)
* Ports available: `3001`, `8001`, `8006`, `8020`, `8030`, `8031`, `8042`, `8045`, `8080`, `5445`, `6387`, `9001`, `9002`

#### Step 1: Build Custom Farmer Images
The Farmer Registry extends the upstream OpenG2P platform base images with the `farmer-extension` package:
```bash
docker compose build
```

#### Step 2: Start the Stack
```bash
docker compose up -d
```

#### Step 3: Initialize Database Seeds & Geography Data
On fresh deployments, load the administrative hierarchies (Regions, Zones, Woredas, Kebeles):
```bash
docker compose run --rm farmer-registry-geo-seed
docker compose run --rm farmer-registry-db-seed
docker compose run --rm farmer-registry-geo-remap
```

#### Step 4: Verify Local Deployment
* **Staff Portal UI**: [http://localhost:3001](http://localhost:3001) (Login: `admin` / `admin`)
* **Staff API Docs**: [http://localhost:8001/docs](http://localhost:8001/docs)
* **Partner API Docs**: [http://localhost:8006/docs](http://localhost:8006/docs)
* **Keycloak Admin**: [http://localhost:8080](http://localhost:8080) (Login: `admin` / `admin`)

---

### 3. Production Deployment (Kubernetes via Helm)

The production deployment uses the **`openg2p-farmer-registry`** Helm wrapper chart. It pins the upstream `openg2p-registry` subchart and injects the farmer-specific Docker images, schemas, and analytics views.

#### Prerequisites
* Kubernetes Cluster v1.23+
* Helm v3.8+
* Cluster Ingress Controller (e.g. NGINX Ingress) with TLS certificates (cert-manager / Let's Encrypt)
* External PostgreSQL 16 (or cloud-managed RDS/CloudSQL)

#### Step 1: Add Helm Repositories & Build Dependencies
The upstream platform chart is hosted on GitLab. Add the official package registry:

```bash
# Add official OpenG2P Helm chart repository
helm repo add openg2p-charts https://gitlab.com/api/v4/projects/84460547/packages/helm/stable
helm repo update

# Build local chart dependencies
helm dependency build ./helm/openg2p-farmer-registry
```

#### Step 2: Configure Production Values (`values-production.yaml`)
Create a custom `values-production.yaml` overlay for your environment:

```yaml
global:
  registryHostname: farmer-registry.yourdomain.org
  ingress:
    enabled: true
    className: nginx
    annotations:
      cert-manager.io/cluster-issuer: letsencrypt-prod
    tls:
      - secretName: farmer-registry-tls
        hosts:
          - farmer-registry.yourdomain.org

# Database Configuration (External PostgreSQL 16)
postgresql:
  enabled: false
externalDatabase:
  host: "postgres-cluster.database.svc"
  port: 5432
  user: "postgres"
  password: "YOUR_DB_PASSWORD"
  database: "farmer_registry_db"

# Object Storage (MinIO / AWS S3)
s3:
  endpoint: "https://s3.amazonaws.com"
  accessKey: "YOUR_S3_ACCESS_KEY"
  secretKey: "YOUR_S3_SECRET_KEY"
  bucket: "farmer-registry-documents"
  region: "us-east-1"

# Production Container Images
registry:
  staffApi:
    image:
      repository: "your-registry.com/farmer-registry/staff-api"
      tag: "v1.2.0"
  partnerApi:
    image:
      repository: "your-registry.com/farmer-registry/partner-api"
      tag: "v1.2.0"
  celery:
    image:
      repository: "your-registry.com/farmer-registry/celery"
      tag: "v1.2.0"
  staffUi:
    image:
      repository: "your-registry.com/farmer-registry/staff-ui"
      tag: "v1.2.0"

  sanity:
    runE2e: true
```

#### Step 3: Deploy to Kubernetes
```bash
# Create namespace
kubectl create namespace openg2p --dry-run=client -o yaml | kubectl apply -f -

# Install or Upgrade release
helm upgrade --install farmer-registry ./helm/openg2p-farmer-registry \
  --namespace openg2p \
  -f ./helm/openg2p-farmer-registry/values.yaml \
  -f values-production.yaml
```

#### Step 4: Verify Kubernetes Rollout
```bash
# Check pod status
kubectl get pods -n openg2p -l app.kubernetes.io/name=farmer-registry

# Check ingress routing
kubectl get ingress -n openg2p

# Stream API logs
kubectl logs -n openg2p -l app.kubernetes.io/component=staff-api --tail=100 -f
```

---

### 4. ODK Field Data Collection Integration

ODK field collection connects to the Farmer Registry via two supported integration patterns:

#### Pattern A: Real-Time Webhooks (Recommended for Server & Production)
1. In **ODK Central** (e.g. `https://odk.yourdomain.org`), navigate to:
   **Project ➔ Form (`ATI_Farmers_Profile_ODK_Form_v2`) ➔ Form Settings ➔ Webhooks**.
2. Click **Create Webhook** and set:
   * **URL**: `https://farmer-registry.yourdomain.org/api/v1/farmer-registry/odk/webhook`
3. Whenever an enumerator submits a finalized form from an Android tablet, ODK Central directly fires an HTTPS POST to OpenG2P, which validates, transforms, and ingests the record automatically into the registry.

#### Pattern B: Automated Scheduled Pull via OpenG2P Connector Service (DevOps Setup Guide)
The OpenG2P Connector Service runs as an automated background bridge between ODK Central and the Farmer Registry. It periodically polls ODK Central via OData, automatically expands nested repeat groups (`land_info_repeat`, `crop_repeat`, `livestock_repeat`), packages submissions in the OpenG2P payload envelope, and forwards them to the Partner API (`/partner/ingest_data`).

##### 1. Database Initialization (PostgreSQL)
Create the dedicated `connector` database in PostgreSQL:
```bash
# In PostgreSQL (via psql or kubectl exec):
CREATE DATABASE connector;
-- Grant access to your PostgreSQL user (e.g. postgres or connector_user)
GRANT ALL PRIVILEGES ON DATABASE connector TO postgres;
```

##### 2. Deploy to Kubernetes Server (`far` or `openg2p` namespace)
DevOps can apply the pre-packaged manifest [`odk/connector-k8s-deployment.yaml`](odk/connector-k8s-deployment.yaml):

1. **Configure Environment Secrets**:
   Edit `odk/connector-k8s-deployment.yaml` to specify your cluster's PostgreSQL password, Redis broker URL, and Partner API internal service name:
   ```yaml
   # Key settings in odk/connector-k8s-deployment.yaml:
   CONNECTOR_PARTNER_INGEST_BASE_URL: "http://farmer-registry-partner-api:8000"
   CONNECTOR_CELERY_BROKER_URL: "redis://farmer-registry-redis:6379/1"
   CONNECTOR_DB_HOSTNAME: "farmer-registry-postgres"
   ```

2. **Apply Manifest**:
   ```bash
   kubectl apply -f odk/connector-k8s-deployment.yaml -n openg2p
   ```
   This deploys three workloads:
   * **`connector-api`**: FastAPI service managing pipeline metadata and REST API (:8050).
   * **`connector-worker`**: Celery Beat scheduler + worker executing automated polling tasks every 5 minutes.
   * **`connector-ui`**: React web dashboard (:80).

3. **Verify Pod Status**:
   ```bash
   kubectl get pods -n openg2p -l app.kubernetes.io/name=connector
   ```

##### 3. Alternative: Docker Compose Deployment (Local / VM)
If running on a virtual machine or local dev stack, add the connector services to your `docker-compose.yml`:
```yaml
connector-api:
  image: openg2p/openg2p-connector-service:latest
  command: ["python3", "-m", "app.main"]
  environment:
    CONNECTOR_DB_HOSTNAME: postgres
    CONNECTOR_DB_PORT: 5432
    CONNECTOR_DB_DBNAME: connector
    CONNECTOR_DB_USERNAME: postgres
    CONNECTOR_DB_PASSWORD: YOUR_POSTGRES_PASSWORD
    CONNECTOR_CELERY_BROKER_URL: redis://redis:6379/1
    CONNECTOR_CELERY_RESULT_BACKEND: redis://redis:6379/1
    CONNECTOR_PARTNER_INGEST_BASE_URL: http://farmer-registry-partner-api:8000
    CONNECTOR_APP_HOST: 0.0.0.0
    CONNECTOR_APP_PORT: 8050
    CONNECTOR_CORS_ORIGINS: "*"
  ports:
    - "8050:8050"

connector-worker:
  image: openg2p/openg2p-connector-service:latest
  command: ["celery", "-A", "app.celery_app", "worker", "--beat", "-l", "info"]
  environment:
    CONNECTOR_DB_HOSTNAME: postgres
    CONNECTOR_DB_PORT: 5432
    CONNECTOR_DB_DBNAME: connector
    CONNECTOR_DB_USERNAME: postgres
    CONNECTOR_DB_PASSWORD: YOUR_POSTGRES_PASSWORD
    CONNECTOR_CELERY_BROKER_URL: redis://redis:6379/1
    CONNECTOR_CELERY_RESULT_BACKEND: redis://redis:6379/1
    CONNECTOR_PARTNER_INGEST_BASE_URL: http://farmer-registry-partner-api:8000

connector-ui:
  image: openg2p/openg2p-connector-ui:latest
  ports:
    - "5173:80"
```

##### 4. Seed the Pipeline Definition (`odk/seed_connector_pipelines.sql`)
Run the seed script against the `connector` PostgreSQL database to configure the polling job:
```bash
# For Kubernetes:
kubectl exec -i $(kubectl get pod -n openg2p -l app.kubernetes.io/name=postgres -o jsonpath='{.items[0].metadata.name}') -n openg2p -- psql -U postgres -d connector < odk/seed_connector_pipelines.sql

# For Docker Compose:
docker exec -i farmer-registry-postgres psql -U postgres -d connector -f odk/seed_connector_pipelines.sql
```

**Configurable fields in `odk/seed_connector_pipelines.sql`**:
| Field | Value | Purpose |
| :--- | :--- | :--- |
| `base_url` | `https://odk.yourdomain.org` | Your ODK Central server URL |
| `project_id` | `13` | ODK Central numeric project ID |
| `form_id` | `farmer_profile` | ODK XLSForm XML form ID |
| `resolve_nav_links`| `true` | Automatically fetches nested ODK repeat groups (lands, crops, livestock) |
| `email` | `enumerator@domain.org` | ODK Central user with Project Viewer role |
| `password` | `odksandbox` | ODK Central user password |
| `target_url` | `http://farmer-registry-partner-api:8000/partner/ingest_data` | Partner API internal URL |
| `target_headers` | `{"partner-id": "farmer-partner"}` | Required partner authentication header |

##### 5. Operational Verification & Troubleshooting
1. **Check Worker Logs**:
   ```bash
   kubectl logs -n openg2p -l app.kubernetes.io/component=worker -f
   ```
   You will see the Celery Beat worker trigger `poll_all` every 5 minutes, download new submissions, and forward them to Partner API.
2. **Access Connector UI**:
   Open `http://<CONNECTOR_UI_HOST>:5173` (or cluster ingress URL). The pipeline `Farmer Registry - ODK Central Ingestion` will show active status, last execution time, and a **"Poll Now"** button for immediate manual synchronization.
3. **Verify Intake Submission**:
   Log in to OpenG2P Staff Portal at `https://<YOUR_DOMAIN>/en/intake-form/farmer` to view the newly ingested drafts ready for staff review and approval.

For complete technical specifications, see [`odk/ODK_CONNECTOR_SERVICE_SETUP_GUIDE.md`](odk/ODK_CONNECTOR_SERVICE_SETUP_GUIDE.md).

---

### 5. Health Checks, Monitoring & Maintenance

#### Health & Readiness Probes
| Service | Endpoint | Success Status |
| :--- | :--- | :--- |
| **Staff API Liveness** | `GET /healthz` | HTTP 200 `{"status": "UP"}` |
| **Staff API Readiness** | `GET /readyz` | HTTP 200 `{"status": "UP"}` |
| **Partner API Health** | `GET /healthz` | HTTP 200 `{"status": "UP"}` |
| **ODK Ingestion Summary** | `GET /api/v1/farmer-registry/odk/summary` | JSON count of ingested records |

#### Upstream Image & Chart Version Maintenance
The farmer container images and Helm chart dependency versions are pinned in lockstep:

```bash
# Check latest published platform version (dry-run, writes nothing):
./scripts/bump-rp-version.sh -n

# Apply a specific platform version to Dockerfiles and Chart.yaml simultaneously:
./scripts/bump-rp-version.sh 1.2.0-rc.384
```

See the official documentation at [docs.openg2p.org](https://docs.openg2p.org).
