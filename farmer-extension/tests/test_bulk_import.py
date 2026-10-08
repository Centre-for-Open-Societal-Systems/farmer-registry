"""Stdlib (+openpyxl) tests for the CSV/XLSX farmer bulk-import core.

Loads the module by path so it does not need openg2p_registry_core.
"""

import importlib.util
import pathlib
import sys
import unittest

_SRC = (pathlib.Path(__file__).parent.parent / "src" / "openg2p_registry_farmer_extension"
        / "bulk_import" / "farmer_import.py")
_spec = importlib.util.spec_from_file_location("farmer_import", _SRC)
fi = importlib.util.module_from_spec(_spec)
sys.modules["farmer_import"] = fi
_spec.loader.exec_module(fi)


class TestBulkImport(unittest.TestCase):
    def test_headers_unique(self):
        self.assertEqual(len(fi.HEADERS), len(set(fi.HEADERS)))

    def test_example_csv_parses_without_errors(self):
        res = fi.rows_to_submissions(fi.read_rows("t.csv", fi.build_csv()))
        self.assertEqual(len(res), 1)
        self.assertTrue(res[0]["ok"], res[0])
        sub = res[0]["submission"]
        self.assertEqual(sub["fr_farmer_personal_info"][0]["import_source"], "IMPORT_FILE")
        self.assertEqual(sub["fr_farmer_personal_info"][0]["gender"], "MALE")
        self.assertEqual(len(sub["intake_fr_farmer_land"]), 1)
        self.assertEqual(sub["fr_household_members"][0]["first_name"], "Almaz")

    def test_csv_and_xlsx_equivalent(self):
        a = fi.rows_to_submissions(fi.read_rows("t.csv", fi.build_csv()))
        b = fi.rows_to_submissions(fi.read_rows("t.xlsx", fi.build_xlsx()))
        self.assertEqual(a, b)

    def test_bad_row_does_not_abort_others(self):
        good = fi.example_rows()[0]
        bad = dict(good, gender="ROBOT")
        missing = dict(good, first_name="")
        res = fi.rows_to_submissions([good, bad, missing])
        self.assertEqual([r["ok"] for r in res], [True, False, False])
        self.assertEqual([r["row"] for r in res], [2, 3, 4])
        self.assertIn("gender", res[1]["errors"][0])

    def test_unknown_column_and_file_type_rejected(self):
        with self.assertRaises(fi.RowError):
            fi.read_rows("t.csv", b"first_name,bogus\nA,B\n")
        with self.assertRaises(fi.RowError):
            fi.read_rows("t.txt", b"x")

    def test_row_limit(self):
        body = "first_name\n" + "A\n" * (fi.MAX_ROWS + 1)
        with self.assertRaises(fi.RowError):
            fi.read_rows("t.csv", body.encode())


if __name__ == "__main__":
    unittest.main()
