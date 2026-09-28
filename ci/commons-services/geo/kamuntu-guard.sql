-- Abort the transaction if kamuntu-scan.sql found anything.
DO $$
DECLARE
    bad text;
BEGIN
    SELECT string_agg(format('%s.%s (%s)', table_name, column_name, n), ', ' ORDER BY table_name, column_name)
      INTO bad
      FROM _kamuntu_hits;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'Kamuntu data still present: %', bad;
    END IF;
END $$;
