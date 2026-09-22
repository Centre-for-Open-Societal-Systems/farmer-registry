-- ==============================================================================
-- OpenG2P Farmer Registry — ODK Connector & Partner Ingestion Configuration Seed
-- Mirrors the OpenG2P standard pipeline (Livestock Registry setup)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. In `farmer_master_data_db`: Partner Registration
-- ------------------------------------------------------------------------------
-- Connect to master data database:
-- \c farmer_master_data_db;

CREATE TABLE IF NOT EXISTS public.g2p_partners (
    partner_id character varying NOT NULL PRIMARY KEY,
    partner_mnemonic character varying NOT NULL UNIQUE,
    keymanager_reference_id character varying NOT NULL UNIQUE,
    is_active boolean DEFAULT true NOT NULL
);

INSERT INTO public.g2p_partners (partner_id, partner_mnemonic, keymanager_reference_id, is_active)
VALUES ('farmer-partner', 'farmer-partner', 'farmer-key-ref', true)
ON CONFLICT (partner_id) DO UPDATE SET
    partner_mnemonic = EXCLUDED.partner_mnemonic,
    is_active = true;


-- ------------------------------------------------------------------------------
-- 2. In `farmer_registry_db`: Data Model, Key Paths, Routing & Templates
-- ------------------------------------------------------------------------------
-- Connect to farmer registry database:
-- \c farmer_registry_db;

-- 2.1 Register Data Model for Celery Worker classification
INSERT INTO public.data_models (
    data_model_id,
    data_model_mnemonic,
    pattern_for_data_model,
    response_template_document_id,
    is_active
) VALUES (
    'FARMER_ODK_MODEL',
    'FARMER_ODK_MODEL',
    '$.body.header.sender_id=>^.*$',
    NULL,
    true
) ON CONFLICT (data_model_id) DO UPDATE SET
    pattern_for_data_model = EXCLUDED.pattern_for_data_model,
    is_active = true;

-- 2.2 Register Incoming Key Paths
INSERT INTO public.incoming_model_key_paths (
    key_path_id,
    data_model_id,
    key_path_for_message_id,
    key_path_for_sender,
    key_path_for_signature,
    key_path_for_signature_payload,
    is_list,
    key_path_for_list_elements
) VALUES (
    'farmer_key_path',
    'FARMER_ODK_MODEL',
    '$.body.header.message_id',
    '$.body.header.sender_id',
    '$.body.header.signature',
    '$.body.message',
    false,
    NULL
) ON CONFLICT (key_path_id) DO UPDATE SET
    key_path_for_message_id = EXCLUDED.key_path_for_message_id,
    key_path_for_sender = EXCLUDED.key_path_for_sender,
    key_path_for_signature = EXCLUDED.key_path_for_signature,
    key_path_for_signature_payload = EXCLUDED.key_path_for_signature_payload;

-- 2.3 Register Semantic Patterns for Ingest Classification Worker
-- Maps the FARMER_ODK_MODEL payload to the Farmer Ingestion Intake form
INSERT INTO public.incoming_model_semantic_patterns (
    semantic_pattern_id,
    data_model_id,
    register_id,
    intake_form_id,
    section_id,
    pattern_for_register,
    pattern_for_intake_form,
    pattern_for_section,
    key_path_for_business_payload,
    raw_payload_enricher_class
) VALUES (
    'farmer_odk_semantic_pattern',
    'FARMER_ODK_MODEL',
    'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd',
    'a1a4d25a-1cd4-4356-abac-8782382649',
    NULL,
    NULL,
    '$.body.header.sender_id=>^.*$',
    NULL,
    '$.body.message',
    'G2PDciFarmerCreateEnricherService'
) ON CONFLICT (semantic_pattern_id) DO UPDATE SET
    register_id = EXCLUDED.register_id,
    intake_form_id = EXCLUDED.intake_form_id,
    pattern_for_intake_form = EXCLUDED.pattern_for_intake_form,
    key_path_for_business_payload = EXCLUDED.key_path_for_business_payload,
    raw_payload_enricher_class = EXCLUDED.raw_payload_enricher_class;

-- 2.4 Register Jinja2 Template Document
INSERT INTO public.g2p_registry_documents (
    document_id,
    document_store_id,
    bucket,
    source_filename,
    created_by,
    created_at
) VALUES (
    'farmer-odk-tmpl-doc',
    'farmer_transform.j2',
    'templates',
    'farmer_transform.j2',
    'system',
    NOW()
) ON CONFLICT (document_id) DO UPDATE SET
    document_store_id = EXCLUDED.document_store_id,
    bucket = EXCLUDED.bucket;

-- 2.5 Link Data Model and Register to Transformation Template
INSERT INTO public.incoming_templates (
    template_id,
    register_id,
    data_model_id,
    template_document_id,
    jsonld_expansion_required,
    created_at
) VALUES (
    'IN-TMPL-ODK',
    'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd',
    'FARMER_ODK_MODEL',
    'farmer-odk-tmpl-doc',
    false,
    NOW()
) ON CONFLICT (template_id) DO UPDATE SET
    template_document_id = EXCLUDED.template_document_id,
    jsonld_expansion_required = EXCLUDED.jsonld_expansion_required;
