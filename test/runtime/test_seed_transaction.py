"""Run inside the seed image against an explicitly named disposable database.

python /repo/test/runtime/test_seed_transaction.py
Requires PG* pointing to a database named coss_seed_test_* or coss_seed_rehearsal_*.
"""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('seed', '/seed/coss_seed.py')
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


class Transactions(unittest.TestCase):
    def setUp(self):
        if not os.environ.get('PGDATABASE', '').startswith(('coss_seed_test_', 'coss_seed_rehearsal_')):
            raise RuntimeError('Disposable seed test database required')
        self.conn = seed.connect()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.conn.close)

    def file(self, name, sql):
        p = Path(self.directory.name) / name
        p.write_text(sql, encoding='utf-8')
        return p

    def test_failure_rolls_back_preceding_file(self):
        first = self.file('01.sql', 'CREATE TABLE coss_seed_rollback_probe(id int);')
        bad = self.file('02.sql', 'SELECT definitely_missing_seed_function();')
        with self.assertRaises(seed.psycopg2.Error):
            seed.apply(self.conn, [first, bad])
        with self.conn.cursor() as cur:
            cur.execute("SELECT to_regclass('coss_seed_rollback_probe')")
            self.assertIsNone(cur.fetchone()[0])

    def test_comment_only_placeholder_is_skipped(self):
        seed.apply(self.conn, [self.file('empty.sql', '-- placeholder\n/* no statements */')])

    def test_repeat_insert_preserves_existing_value(self):
        with self.conn.cursor() as cur:
            cur.execute('CREATE TEMP TABLE seed_repeat_probe(id int primary key, value text)')
        p = self.file('repeat.sql', "INSERT INTO seed_repeat_probe VALUES(1,'original') ON CONFLICT DO NOTHING;")
        seed.apply(self.conn, [p])
        seed.apply(self.conn, [p])
        with self.conn.cursor() as cur:
            cur.execute('SELECT count(*), min(value) FROM seed_repeat_probe')
            self.assertEqual(cur.fetchone(), (1, 'original'))

    def test_reporting_optional_main_crops_on_both_schema_shapes(self):
        # Execute the actual reporting SQL's lateral projection, not a copy.
        sql = Path('/seed/reporting_views.sql').read_text(encoding='utf-8')
        start = sql.index('CROSS JOIN LATERAL (\n    SELECT CASE WHEN jsonb_typeof')
        stop = sql.index(') mc', start) + len(') mc')
        projection = sql[start:stop]
        with self.conn.cursor() as cur:
            cur.execute('CREATE TEMP TABLE reporting_crop_probe(id int)')
            cur.execute('INSERT INTO reporting_crop_probe VALUES(1)')
            query = 'SELECT mc.main_crops, mc.main_crop_count FROM reporting_crop_probe f ' + projection
            cur.execute(query)
            self.assertEqual(cur.fetchone(), (None, None))
            cur.execute('ALTER TABLE reporting_crop_probe ADD COLUMN main_crops jsonb')
            for value, expected in [('[]', ([], 0)), ('["maize","teff"]', (["maize", "teff"], 2)),
                                    ('"malformed-scalar"', (None, None))]:
                cur.execute('UPDATE reporting_crop_probe SET main_crops=%s::jsonb', (value,))
                cur.execute(query)
                self.assertEqual(cur.fetchone(), expected)


if __name__ == '__main__':
    unittest.main()
