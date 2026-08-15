-- PostgreSQL Migration Script for OpenG2P Farmer & Land Registry
-- This script safely adds the newly configured metadata columns to the existing tables.
-- Your colleague can run this directly in pgAdmin or via psql:
-- psql -U postgres -d registry_db_v2 -f farmer_schema_migration.sql

-- 1. Update Farmer Tables
DO $$
DECLARE
    table_name text;
BEGIN
    FOR table_name IN SELECT unnest(ARRAY[
        'g2p_register_farmers', 
        'g2p_intake_form_farmers', 
        'g2p_register_history_farmers'
    ]) LOOP
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS email TEXT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS personal_phone_number BOOLEAN;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS date_of_birth_gc TEXT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS date_of_birth_ec TEXT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS age INTEGER;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS is_household_head BOOLEAN;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS psnp_user BOOLEAN;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS do_you_use_machinery BOOLEAN;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS what_kind_of_machinery_do_you_use TEXT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS do_you_have_financial_access BOOLEAN;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS what_financial_services_do_you_use TEXT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS region TEXT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS zone TEXT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS woreda TEXT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS kebele TEXT;';
        
        -- JSONB Columns for Complex Arrays and Objects
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS household JSONB;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS farmer JSONB;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS consent_requests JSONB;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS consent_receipts JSONB;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS records JSONB;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS documents JSONB;';
    END LOOP;
END $$;


-- 2. Update Land Tables
DO $$
DECLARE
    table_name text;
BEGIN
    FOR table_name IN SELECT unnest(ARRAY[
        'g2p_register_lands', 
        'g2p_intake_form_lands', 
        'g2p_register_history_lands'
    ]) LOOP
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS total_owned_land FLOAT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS total_rented_land FLOAT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS total_crop_sharing_land FLOAT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS total_land_area FLOAT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS land_ownership TEXT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS remark TEXT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS land_id TEXT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS certificate_provider TEXT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS land_certificate TEXT;';
        EXECUTE 'ALTER TABLE ' || table_name || ' ADD COLUMN IF NOT EXISTS integration_status TEXT;';
    END LOOP;
END $$;
