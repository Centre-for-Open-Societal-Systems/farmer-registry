-- "Import from file" entry for the Farmer intake form (farmer_ingestion_intake),
-- the staff portal's native bulk upload (OpenG2P registry design: bulk upload).
-- Its file-import data model (file_import_to_farmer_intake, seeded in
-- zz-oan/61_file_import_to_farmer_intake.sql) has key paths, a pass-through
-- pattern and a Jinja template that take one flat CSV/Excel row per intake. The
-- ODK data model (odk_to_farmer_intake) belongs to the ODK connector and is not
-- used here. The configuration id is fixed
-- (uuid5(NAMESPACE_URL, 'urn:oan:import-file-configuration:file_import_to_farmer_intake'))
-- and the row is upserted, so an upgrade updates it in place and the seed can
-- run again. The template mnemonic is the name staff see under Import from file;
-- the import itself is routed by data_model_id.
-- Columns: docs/file-import.md.

INSERT INTO g2p_registry_import_file_configurations (
    import_file_configuration_id,
    register_id,
    form_id,
    data_model_id,
    import_file_template_mnemonic,
    import_file_template_description
) VALUES
(
    'eeb09070-dbde-56b4-b0a8-bb8acbb51c47',
    'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd',
    'a1a4d25a-1cd4-4356-abac-8782382649',
    'file_import_to_farmer_intake',
    'Farmer intake',
    'Import farmer intakes from a CSV or Excel file, one row per farmer'
)
ON CONFLICT (import_file_configuration_id) DO UPDATE SET
    register_id = EXCLUDED.register_id,
    form_id = EXCLUDED.form_id,
    data_model_id = EXCLUDED.data_model_id,
    import_file_template_mnemonic = EXCLUDED.import_file_template_mnemonic,
    import_file_template_description = EXCLUDED.import_file_template_description;
