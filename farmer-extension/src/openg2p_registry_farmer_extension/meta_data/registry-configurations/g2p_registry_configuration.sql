INSERT INTO
    "public"."g2p_registry_configuration" (
        "configuration_id",
        "registry_name",
        "registry_logo",
        "registry_favicon",
        "registry_theme_id",
        "registry_language_id"
    )
VALUES
    (
        'c4238735-e688-44b0-a4f4-2dfafe45c031',
        'Farmer Registry',
        NULL,
        NULL,
        '68721343-ea47-4675-94da-0437d688e9fe',
        'ccbcb97b-c4df-415d-9e4d-ec4985cf04e9'
    )
ON CONFLICT ("configuration_id") DO UPDATE SET "registry_name" = EXCLUDED."registry_name", "registry_logo" = EXCLUDED."registry_logo", "registry_favicon" = EXCLUDED."registry_favicon", "registry_theme_id" = EXCLUDED."registry_theme_id", "registry_language_id" = EXCLUDED."registry_language_id";
