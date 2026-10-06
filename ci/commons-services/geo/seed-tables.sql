-- Staging tables the location seed is loaded into before anything touches the
-- real ones. seed_rows() in geo-common.sh retargets the seed's INSERTs here, so
-- the seed can be compared against what is already there, and so the same rows
-- can be used in a registry database, which has no geo tables of its own.
--
-- Same columns as the seed's INSERTs; the keys match the real tables, so the
-- seed's own ON CONFLICT clauses resolve against them.
CREATE TEMP TABLE _seed_levels (
    level_id          varchar PRIMARY KEY,
    level_mnemonic    varchar NOT NULL UNIQUE,
    parent_level_id   varchar,
    display_name      varchar,
    display_name_i18n jsonb,
    version           varchar,
    valid_from        date,
    valid_to          date
) ON COMMIT DROP;

CREATE TEMP TABLE _seed_values (
    level_value_id          varchar PRIMARY KEY,
    level_id                varchar NOT NULL,
    level_value_mnemonic    varchar NOT NULL,
    parent_level_value_id   varchar,
    pcode                   varchar,
    pcode_source            varchar,
    boundary_uri            varchar,
    boundary_simplified_uri varchar,
    display_name            varchar,
    display_name_i18n       jsonb,
    version                 varchar,
    valid_from              date,
    valid_to                date
) ON COMMIT DROP;
