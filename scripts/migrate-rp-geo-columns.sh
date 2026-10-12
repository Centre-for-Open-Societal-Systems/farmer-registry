#!/usr/bin/env bash
# Run with PostgreSQL 16 client tools and PGDATABASE/PGUSER set. Repairs the
# legacy varchar G2PGeo columns for registry-platform 1.2.2. Stops on invalid
# numbers; backs up data; rebuilds reporting views with their definitions,
# owners, grants and indexes preserved. No seed data is loaded.
# Example inside local postgres: PGDATABASE=farmer_registry_db PGUSER=postgres \
#   bash /tmp/migrate-rp-geo-columns.sh /tmp/farmer-geo-backup
set -euo pipefail
: "${PGDATABASE:?Set PGDATABASE to the farmer registry database}"
backup=${1:?Pass a new backup directory}
remaining=$(psql -X -v ON_ERROR_STOP=1 -Atc "SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND data_type IN ('text','character varying') AND column_name IN ('latitude','longitude','altitude') AND table_name ~ '^g2p_(register_|register_history_|intake_form_)(farmers|households|household_members|lands)$'")
if [ "$remaining" = 0 ]; then
  echo 'Coordinate types already match rc.544; no changes needed.'
  exit 0
fi
mkdir "$backup"
pg_dump -Fc -f "$backup/database.dump"

# pg_dump emits materialized views WITH NO DATA. Save their dependency order
# before dropping them so refreshes can populate parents before their children.
psql -X -v ON_ERROR_STOP=1 -At > "$backup/view-order.tsv" <<'SQL'
WITH RECURSIVE views AS (
  SELECT oid, relname, relkind FROM pg_class
  WHERE relnamespace = 'public'::regnamespace
    AND relname LIKE 'fr_rpt_%' AND relkind IN ('v','m')
), edges AS (
  SELECT DISTINCT r.ev_class AS child, d.refobjid AS parent
  FROM pg_depend d JOIN pg_rewrite r ON r.oid=d.objid
  WHERE r.ev_class IN (SELECT oid FROM views)
    AND d.refobjid IN (SELECT oid FROM views) AND r.ev_class <> d.refobjid
), levels AS (
  SELECT oid, 0 AS depth FROM views
  UNION ALL
  SELECT e.child, l.depth+1 FROM levels l JOIN edges e ON e.parent=l.oid
)
SELECT max(l.depth) || E'\t' || v.relkind::text || E'\t' || quote_ident(v.relname)
FROM views v JOIN levels l ON l.oid=v.oid
GROUP BY v.oid,v.relkind,v.relname ORDER BY max(l.depth),v.relname;
SQL
if [ -s "$backup/view-order.tsv" ]; then
  pg_dump --schema-only -t 'public.fr_rpt_*' > "$backup/reporting.sql"
else
  : > "$backup/reporting.sql"
fi

cat > "$backup/migrate.sql" <<'SQL'
BEGIN;
SET LOCAL lock_timeout = '10s';
-- Validate all values before altering anything. Blank legacy inputs mean NULL;
-- nonempty invalid data aborts the entire transaction instead of being lost.
DO $$
DECLARE c record; invalid bigint;
BEGIN
  FOR c IN SELECT table_name,column_name FROM information_schema.columns
    WHERE table_schema='public' AND data_type IN ('text','character varying')
      AND column_name IN ('latitude','longitude','altitude')
      AND table_name ~ '^g2p_(register_|register_history_|intake_form_)(farmers|households|household_members|lands)$'
  LOOP
    EXECUTE format('SELECT count(*) FROM public.%I WHERE NULLIF(btrim(%I), '''') IS NOT NULL AND NOT pg_input_is_valid(btrim(%I), ''double precision'')', c.table_name,c.column_name,c.column_name) INTO invalid;
    IF invalid > 0 THEN
      RAISE EXCEPTION '%.% has % invalid coordinate values; no changes committed', c.table_name,c.column_name,invalid;
    END IF;
  END LOOP;
END $$;
SQL

# RESTRICT is deliberate: an unexpected dependent object aborts the transaction
# and preserves the database rather than being removed by CASCADE.
sort -rn "$backup/view-order.tsv" | while IFS=$'\t' read -r depth kind name; do
  if [ "$kind" = m ]; then
    printf 'DROP MATERIALIZED VIEW public.%s;\n' "$name"
  else
    printf 'DROP VIEW public.%s;\n' "$name"
  fi
done >> "$backup/migrate.sql"

cat >> "$backup/migrate.sql" <<'SQL'
DO $$
DECLARE c record;
BEGIN
  FOR c IN SELECT table_name,column_name FROM information_schema.columns
    WHERE table_schema='public' AND data_type IN ('text','character varying')
      AND column_name IN ('latitude','longitude','altitude')
      AND table_name ~ '^g2p_(register_|register_history_|intake_form_)(farmers|households|household_members|lands)$'
  LOOP
    EXECUTE format('ALTER TABLE public.%I ALTER COLUMN %I TYPE double precision USING NULLIF(btrim(%I), '''')::double precision', c.table_name,c.column_name,c.column_name);
  END LOOP;
END $$;
SQL
cat "$backup/reporting.sql" >> "$backup/migrate.sql"
while IFS=$'\t' read -r depth kind name; do
  if [ "$kind" = m ]; then
    printf 'REFRESH MATERIALIZED VIEW public.%s;\n' "$name"
  fi
done < "$backup/view-order.tsv" >> "$backup/migrate.sql"
printf 'COMMIT;\n' >> "$backup/migrate.sql"
psql -X -v ON_ERROR_STOP=1 -f "$backup/migrate.sql"
printf 'Coordinate migration complete. Backup and exact SQL: %s\n' "$backup"
