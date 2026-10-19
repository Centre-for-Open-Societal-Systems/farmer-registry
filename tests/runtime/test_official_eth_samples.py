"""Run with PG* pointing only at a restored farmer_seed_rehearsal_* DB."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


samples = module("official_eth", "docker/db-seed/import_official_eth_samples.py")
repair = module("projection_repair", "scripts/operations/staging/repair_location_projections.py")


@unittest.skipUnless(os.environ.get("FARMER_LOCATION_TEST_CATALOG"), "Requires isolated restored database")
class OfficialSamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg2
        cls.connection = psycopg2.connect("")
        with cls.connection.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0].startswith("farmer_seed_rehearsal_")
        pack = Path('/openg2p-data/packs/ETH/samples')
        cls.people = json.loads((pack/'individuals.json').read_text())
        cls.households = json.loads((pack/'households.json').read_text())
        cls.records = samples.generate(cls.people, cls.households)
        cls.catalog = json.loads(Path(os.environ['FARMER_LOCATION_TEST_CATALOG']).read_text())

    def setUp(self):
        with self.connection.cursor() as cur:
            for table in ['g2p_register_farmers', 'g2p_register_households']:
                cur.execute('DELETE FROM '+table+' WHERE created_by=%s', (samples.MARKER,))
        self.connection.commit()

    def snapshot(self):
        with self.connection.cursor() as cur:
            cur.execute("SELECT to_jsonb(f) FROM g2p_register_farmers f WHERE created_by<>%s ORDER BY internal_record_id", (samples.MARKER,))
            return cur.fetchall()

    def test_import_official_27_preserves_real_farmer_and_reruns(self):
        before = self.snapshot()
        result = samples.apply(self.connection, self.records, rehearsal=True)
        self.assertEqual((result['insertedFarmers'],result['insertedHouseholds']), (21,6))
        self.assertEqual(self.snapshot(), before)
        again = samples.apply(self.connection, self.records, rehearsal=True)
        self.assertEqual((again['insertedFarmers'],again['insertedHouseholds']), (0,0))
        with self.connection.cursor() as cur:
            cur.execute("SELECT count(*),count(*) FILTER(WHERE geo_lowest_level_value_id IS NOT NULL),count(*) FILTER(WHERE latitude IS NOT NULL AND longitude IS NOT NULL) FROM g2p_register_farmers WHERE created_by=%s", (samples.MARKER,))
            self.assertEqual(cur.fetchone(), (21,0,21))

    def test_failure_rolls_back_both_tables(self):
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError,'Injected'):
            samples.apply(self.connection, self.records, rehearsal=True, fail_after_insert=True)
        self.assertEqual(self.snapshot(),before)
        with self.connection.cursor() as cur:
            for table in self.records:
                cur.execute('SELECT count(*) FROM '+table+' WHERE created_by=%s', (samples.MARKER,))
                self.assertEqual(cur.fetchone()[0],0)

    def test_projection_repair_changes_only_derived_fields_and_reruns(self):
        before=self.snapshot()
        fields={'region_name','zone_name','woreda_name','kebele_name','woreda_level_value_id','geo_code_hierarchy_json'}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'audit.json'
            plan=repair.repair_projections(self.connection,self.catalog,None,rehearsal=True)
            self.assertEqual(self.snapshot(),before)
            result=repair.repair_projections(self.connection,self.catalog,path,rehearsal=True,dry_run=False)
            self.assertEqual(result['repaired'],plan['plannedRepairs'])
            after=self.snapshot()
            self.assertEqual([{k:v for k,v in r[0].items() if k not in fields} for r in before],
                             [{k:v for k,v in r[0].items() if k not in fields} for r in after])
            self.assertEqual(repair.repair_projections(self.connection,self.catalog,None,rehearsal=True)['plannedRepairs'],0)
            self.assertTrue(path.exists())

    def test_wrong_db_and_changed_source_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            samples.apply(self.connection,self.records)
        with self.assertRaisesRegex(ValueError,'reviewed'):
            samples.generate(self.people[:-1],self.households)

    def test_operator_cli_transaction_lifecycle(self):
        base=[sys.executable,str(ROOT/'docker/db-seed/import_official_eth_samples.py'),'--environment','staging','--namespace','far','--rehearsal','--apply']
        result=subprocess.run(base,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['insertedFarmers'],21)
        again=subprocess.run(base,capture_output=True,text=True)
        self.assertEqual(again.returncode,0,again.stderr)
        self.assertEqual(json.loads(again.stdout)['insertedFarmers'],0)
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run([sys.executable,str(ROOT/'scripts/operations/staging/repair_location_projections.py'),'--environment','staging','--namespace','far','--rehearsal','--catalog',os.environ['FARMER_LOCATION_TEST_CATALOG'],'--apply','--audit',str(Path(directory)/'audit.json')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main()
