-- Farmer Registry — local database bootstrap.
--
-- Replaces the chart's `postgres-init` Jobs (openg2p/postgres-init:1.2.0), which
-- create one database + owner per component against a shared Postgres. Passwords
-- come from Helm-generated Secrets there; here they are the local-only values in
-- local/.env and must be kept in step with it.
--
-- Runs once, on first initialisation of the postgres volume. To re-run it:
--   docker compose --env-file local/.env down -v

-- Registry (staff-api, partner-api, celery, db-seed). The platform images run
-- their own migrations at startup, so only the database and owner are needed.
CREATE ROLE farmer_user WITH LOGIN PASSWORD 'farmer_pass';
CREATE DATABASE farmer OWNER farmer_user;

-- Master data (geo hierarchy, code lists). The registry APIs read this database
-- directly in addition to calling the master-data API.
CREATE ROLE master_data_user WITH LOGIN PASSWORD 'master_data_pass';
CREATE DATABASE master_data OWNER master_data_user;

-- IAM staff portal API (roles -> permissions, login providers, refresh tokens).
CREATE ROLE iam_user WITH LOGIN PASSWORD 'iam_pass';
CREATE DATABASE iam OWNER iam_user;

-- Keycloak's own store.
CREATE ROLE keycloak_user WITH LOGIN PASSWORD 'keycloak_pass';
CREATE DATABASE keycloak OWNER keycloak_user;

-- Functional ID generator pools (farmer, household).
CREATE ROLE farmer_idgenerator_user WITH LOGIN PASSWORD 'farmer_idgenerator_pass';
CREATE DATABASE farmer_idgenerator OWNER farmer_idgenerator_user;

-- The chart requests pg_trgm for master_data (fuzzy search on geo values).
-- CREATE EXTENSION needs superuser, so it is done here rather than by the app.
\connect master_data
CREATE EXTENSION IF NOT EXISTS pg_trgm;
GRANT ALL ON SCHEMA public TO master_data_user;

-- Postgres 15+ revokes CREATE on public from non-owners, which breaks the
-- platform's Alembic migrations. Grant it back per database.
\connect farmer
GRANT ALL ON SCHEMA public TO farmer_user;
-- The register tables carry a GIN trigram index on search_text, so the registry
-- database needs pg_trgm as much as master_data does. Without it every register
-- migration aborts on `operator class "gin_trgm_ops" does not exist` and the
-- record tables (g2p_register_farmers and friends) are never created.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

\connect iam
GRANT ALL ON SCHEMA public TO iam_user;

\connect farmer_idgenerator
GRANT ALL ON SCHEMA public TO farmer_idgenerator_user;
