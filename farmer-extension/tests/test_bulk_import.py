"""Stdlib (+openpyxl) tests for the CSV/XLSX farmer bulk-import core.

Loads the module by path so it does not need openg2p_registry_core.
"""

import io
import unittest
from datetime import datetime

from bulk_import_test_support import fi


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
        body = "first_name,father_first_name\n" + "A,B\n" * (fi.MAX_ROWS + 1)
        with self.assertRaises(fi.RowError):
            fi.read_rows("t.csv", body.encode())

    def test_invalid_numbers_do_not_abort_batch(self):
        for value in ("inf", "-inf", "NaN", "1e999", "2.8", "-1"):
            with self.subTest(value=value):
                good = fi.example_rows()[0]
                result = fi.rows_to_submissions([dict(good, estimated_age=value), good])
                self.assertEqual([r['ok'] for r in result], [False, True])

    def test_zero_animals_preserved(self):
        row = dict(fi.example_rows()[0], livestock_1_head_count="0")
        self.assertEqual(fi.row_to_submission(row)['fr_farmer_livestocks'][0]['head_count'], 0)

    def test_dates_use_the_correct_calendar(self):
        for key, value, valid in [
            ('birth_date', '2026-99-99', False), ('birth_date', '2023-02-29', False),
            ('birth_date', '2024-02-29', True), ('birth_date', '2024-2-9', False),
            ('birth_date_ec', '2015-13-06', True), ('birth_date_ec', '2016-13-06', False),
            ('birth_date_ec', '2016-13-05', True), ('birth_date_ec', '0000-01-01', False),
        ]:
            with self.subTest(key=key, value=value):
                result = fi.rows_to_submissions([dict(fi.example_rows()[0], **{key: value})])
                self.assertEqual(result[0]['ok'], valid)

    def test_farm_access_survives_without_input_use(self):
        base = {'first_name': 'Abebe', 'father_first_name': 'Kebede'}
        for key, value in [('water_source', 'RAINFED'), ('access_to_finance', 'yes'),
                           ('access_to_machinery', 'no'), ('amount_fertilizer_utilized', '0')]:
            with self.subTest(key=key):
                output = fi.row_to_submission(dict(base, **{key: value}))
                self.assertIn(key, output['fr_farmer_farm_input'][0])

    def test_invalid_file_structure(self):
        for content in [b'', b'first_name\nA', b'first_name,first_name\nA,B',
                        b'first_name,father_first_name,typo\n', b'first_name,,father_first_name\nA,B,C',
                        b'first_name,father_first_name\n', b'first_name,father_first_name\nA,B,C',
                        b'\xff\xfe\xfa']:
            with self.subTest(content=content), self.assertRaises(fi.RowError):
                fi.read_rows('t.csv', content)
        with self.assertRaises(fi.RowError):
            fi.read_rows('t.xlsx', b'not a workbook')
        with self.assertRaises(fi.RowError):
            fi.read_rows('t.csv', b'x' * (fi.MAX_FILE_BYTES + 1))

    def test_blank_rows_preserve_source_numbers(self):
        rows = fi.read_rows('t.csv', b'first_name,father_first_name\nA,B\n,\n\nC,D\n')
        self.assertEqual([r['row'] for r in fi.rows_to_submissions(rows)], [2, 5])

    def test_xlsx_native_date_and_row_number(self):
        from openpyxl import Workbook
        wb = Workbook()
        wb.active.append(['first_name', 'father_first_name', 'birth_date'])
        wb.active.append([None, None, None])
        wb.active.append(['Abebe', 'Kebede', datetime(2000, 2, 29)])
        data = io.BytesIO()
        wb.save(data)
        result = fi.rows_to_submissions(fi.read_rows('t.xlsx', data.getvalue()))[0]
        self.assertEqual(result['row'], 3)
        self.assertEqual(result['submission']['fr_farmer_birth_information'][0]['birth_date'], '2000-02-29')

    def test_maximum_batch(self):
        content = b'first_name,father_first_name\n' + b'Abebe,Kebede\n' * fi.MAX_ROWS
        result = fi.rows_to_submissions(fi.read_rows('t.csv', content))
        self.assertEqual(len(result), 1000)
        self.assertTrue(all(r['ok'] for r in result))


if __name__ == "__main__":
    unittest.main()
