-- Databases needed to run the Farmer Registry locally. Runs once on first
-- Postgres container start (docker-entrypoint-initdb.d).

SELECT 'CREATE DATABASE farmer_registry_db OWNER postgres'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'farmer_registry_db')\gexec

SELECT 'CREATE DATABASE farmer_master_data_db OWNER postgres'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'farmer_master_data_db')\gexec

-- IAM Staff Portal API
SELECT 'CREATE DATABASE iam_staff OWNER postgres'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'iam_staff')\gexec

-- Approval Workflow Engine (AWE)
SELECT 'CREATE DATABASE awe OWNER postgres'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'awe')\gexec

-- OpenG2P ID Generator (functional / registry IDs)
SELECT 'CREATE DATABASE idgenerator OWNER postgres'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'idgenerator')\gexec

-- Required for registry search indexes (search_text trigram index)
\c farmer_registry_db
CREATE EXTENSION IF NOT EXISTS pg_trgm;
