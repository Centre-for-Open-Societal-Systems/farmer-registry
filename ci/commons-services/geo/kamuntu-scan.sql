-- Every trace of Kamuntu, the fictitious sample country, in the current
-- database: any text/json column mentioning "kamuntu", and any country column
-- holding its codes (KM, XKM). Base tables only; views and materialized views
-- are derived and follow once their sources are clean.
--
-- Leaves the hits in _kamuntu_hits for the caller to print or guard on. Needs a
-- write transaction for the temp table; readings run it inside BEGIN .. ROLLBACK.
CREATE TEMP TABLE _kamuntu_hits ON COMMIT DROP AS
SELECT table_name, column_name, n
  FROM (SELECT c.table_name, c.column_name,
               (xpath('/row/n/text()', query_to_xml(format(
                   CASE WHEN c.column_name IN ('country', 'country_code')
                        THEN 'SELECT count(*) AS n FROM %I.%I WHERE %I::text ILIKE %L OR %I::text IN (''KM'', ''XKM'')'
                        ELSE 'SELECT count(*) AS n FROM %I.%I WHERE %I::text ILIKE %L'
                   END,
                   c.table_schema, c.table_name, c.column_name, '%kamuntu%', c.column_name),
                   false, true, '')))[1]::text::bigint AS n
          FROM information_schema.columns c
          JOIN information_schema.tables t
            ON t.table_schema = c.table_schema AND t.table_name = c.table_name
           AND t.table_type = 'BASE TABLE'
         WHERE c.table_schema = 'public'
           AND c.data_type IN ('text', 'character varying', 'json', 'jsonb')) x
 WHERE n > 0;
