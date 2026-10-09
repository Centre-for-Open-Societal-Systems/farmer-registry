"""The Farmer models must survive the platform's own record serialisation.

The platform reads a record column by column: intake_form_data_service's
_serialize_model (every intake section save), the change-request and
register services all do getattr(row, column.name) for column in
inspect(model).columns. A mapped SQL expression (a column_property over
func.coalesce, say) is listed there under an anonymous name like
"%(1234 coalesce)s", so that getattr raises and every intake save answered
SYS-ERR-001. These tests run that same loop over the three Farmer models.

Imports openg2p_registry_core, so it runs in the staff-api container, like
test_intake_server_validation.py.
"""

import unittest

from sqlalchemy import inspect, select
from sqlalchemy.dialects import postgresql

from openg2p_registry_farmer_extension.register_domain.models.farmer import (
    G2PIntakeFormFarmer,
    G2PRegisterFarmer,
    G2PRegisterHistoryFarmer,
)

MODELS = (G2PRegisterFarmer, G2PRegisterHistoryFarmer, G2PIntakeFormFarmer)


class TestPlatformSerialisation(unittest.TestCase):
    def test_every_mapper_column_is_readable_by_name(self):
        for model in MODELS:
            with self.subTest(model=model.__name__):
                row = model()
                # What intake_form_data_service._serialize_model does.
                serialised = {
                    column.name: getattr(row, column.name)
                    for column in inspect(model).columns
                }
                self.assertIn("first_name_amh", serialised)

    def test_local_name_is_not_a_mapper_column(self):
        for model in MODELS:
            with self.subTest(model=model.__name__):
                self.assertNotIn("record_name_local", inspect(model).columns)


class TestRecordNameLocal(unittest.TestCase):
    def test_amharic_name_comes_first(self):
        farmer = G2PRegisterFarmer(
            first_name_amh="አበበ", last_name_amh="ከበደ", first_name_om="Abbabaa"
        )
        self.assertEqual(farmer.record_name_local, "አበበ ከበደ")

    def test_falls_back_to_afaan_oromo(self):
        farmer = G2PIntakeFormFarmer(
            first_name_amh="", first_name_om="Caaltuu", middle_name_om="Tolaa"
        )
        self.assertEqual(farmer.record_name_local, "Caaltuu Tolaa")

    def test_no_local_name_is_none(self):
        self.assertIsNone(G2PRegisterHistoryFarmer().record_name_local)

    def test_register_list_can_sort_on_it(self):
        # _apply_register_record_sort: getattr(model, sort_by).asc()
        query = select(G2PRegisterFarmer.internal_record_id).order_by(
            getattr(G2PRegisterFarmer, "record_name_local").asc()
        )
        sql = str(query.compile(dialect=postgresql.dialect()))
        self.assertIn("coalesce", sql)
        self.assertIn("first_name_amh", sql)
        self.assertIn("first_name_om", sql)


if __name__ == "__main__":
    unittest.main()
