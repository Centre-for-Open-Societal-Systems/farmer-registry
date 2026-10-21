CREATE DATABASE farmer_registry_db;
CREATE DATABASE farmer_master_data_db;
CREATE DATABASE farmer_iam;
CREATE DATABASE farmer_awe;
CREATE DATABASE farmer_idgenerator;
CREATE DATABASE keycloak;
CREATE DATABASE partner_management_db;
CREATE DATABASE consent_manager_db;
CREATE DATABASE audit_manager;
CREATE DATABASE farmer_connector;

\connect farmer_registry_db
CREATE EXTENSION IF NOT EXISTS pg_trgm;
\connect farmer_awe
CREATE EXTENSION IF NOT EXISTS pg_trgm;
