"""Integration-boundary proof for the intake photo fix.

The browser-side patch stamps `record_image_document_id` onto every record of a
section. Everything downstream of that is somebody else's contract, and a patch
that writes a field the backend silently drops would look fixed and still lose
the photo. This asserts the field actually survives each hop, against the REAL
SQLAlchemy models and a real database engine -- no mocks of the layer under test.

Chain being proved:
  1. the farmer INTAKE table physically has a record_image_document_id column
     (it is inherited from G2PRegister, not declared in the farmer extension,
     so this is exactly the kind of thing that silently disappears)
  2. _build_record_data keeps the field when building an intake row -- it filters
     to the model's real columns, so an absent column means a dropped photo
  3. the intake -> live-register promotion carries it across, including through
     the Pydantic schema round-trip that step performs
  4. the LIVE register table has the column too, so it has somewhere to land

Run against a real Postgres (the models use JSONB, which SQLite cannot render):
  docker run -d --name pg -e POSTGRES_PASSWORD=pw -p 55999:5432 postgres:16
  PGURL=postgresql://postgres:pw@host:55999/postgres python test/staff-ui/test_photo_field_persistence.py
"""

import os
import unittest

from sqlalchemy import create_engine, inspect

FIELD = "record_image_document_id"
PGURL = os.environ.get("PGURL")


class TestPhotoFieldSurvivesTheChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from openg2p_registry_farmer_extension.register_domain.models.farmer import (
            G2PIntakeFormFarmer,
            G2PRegisterFarmer,
        )
        from openg2p_registry_farmer_extension.register_domain.schemas.farmer import (
            G2PIntakeFormSchemaFarmer,
        )

        cls.intake_model = G2PIntakeFormFarmer
        cls.register_model = G2PRegisterFarmer
        cls.intake_schema = G2PIntakeFormSchemaFarmer

    # 1 + 4: the column must exist on both tables.
    def test_intake_table_has_the_column(self):
        cols = {c.name for c in self.intake_model.__table__.columns}
        self.assertIn(FIELD, cols, f"{self.intake_model.__tablename__} cannot store the photo id")

    def test_live_register_table_has_the_column(self):
        cols = {c.name for c in self.register_model.__table__.columns}
        self.assertIn(FIELD, cols, f"{self.register_model.__tablename__} cannot store the photo id")

    # 2: the service builds rows by filtering to real columns. This is the step
    # that would silently drop the photo id if the column were missing.
    def test_build_record_data_keeps_the_field(self):
        from openg2p_registry_core.services.intake_form_data_service import (
            G2PIntakeFormDataService,
        )

        service = G2PIntakeFormDataService()
        payload = {
            "internal_record_id": "rec-1",
            "first_name": "Abebe",
            FIELD: "doc-123",
        }
        built = service._build_record_data(payload, payload, self.intake_model)
        self.assertEqual(built.get(FIELD), "doc-123", "intake row build dropped the photo id")
        self.assertEqual(built.get("first_name"), "Abebe", "unrelated field lost")

    # The same builder is used for the intake -> live register promotion, so
    # prove the field survives that call shape too.
    def test_build_record_data_keeps_the_field_for_live_register(self):
        from openg2p_registry_core.services.intake_form_data_service import (
            G2PIntakeFormDataService,
        )

        service = G2PIntakeFormDataService()
        payload = {"internal_record_id": "rec-1", FIELD: "doc-123"}
        built = service._build_record_data(payload, payload, self.register_model)
        self.assertEqual(
            built.get(FIELD), "doc-123", "promotion to the live register dropped the photo id"
        )

    # 3: the promotion step round-trips the intake row through a Pydantic schema.
    def test_schema_round_trip_keeps_the_field(self):
        self.assertIn(
            FIELD,
            self.intake_schema.model_fields,
            "intake schema drops the photo id, so promotion to the live register would lose it",
        )
        inst = self.intake_schema(**{"internal_record_id": "rec-1", FIELD: "doc-123"})
        self.assertEqual(inst.model_dump().get(FIELD), "doc-123")

    # The column must survive an actual CREATE TABLE, not just the ORM mapping.
    # Needs real Postgres: these models use JSONB.
    @unittest.skipUnless(PGURL, "set PGURL to run the real-database checks")
    def test_column_exists_after_real_create_table(self):
        engine = create_engine(PGURL)
        for model in (self.intake_model, self.register_model):
            model.__table__.create(bind=engine, checkfirst=True)
        insp = inspect(engine)
        for model in (self.intake_model, self.register_model):
            cols = {c["name"] for c in insp.get_columns(model.__tablename__)}
            self.assertIn(FIELD, cols, f"{model.__tablename__} DDL has no {FIELD}")

    # End to end: write a row carrying the photo id, read it back.
    @unittest.skipUnless(PGURL, "set PGURL to run the real-database checks")
    def test_round_trip_through_a_real_database(self):
        from datetime import datetime

        from sqlalchemy.orm import Session

        # submission_id is a real UUID column; created_by/created_at and the
        # approval stamps are NOT NULL on the register base.
        submission_id = "11111111-1111-4111-8111-111111111111"
        record_id = "rec-photo-1"
        now = datetime.now()

        engine = create_engine(PGURL)
        self.intake_model.__table__.create(bind=engine, checkfirst=True)
        with Session(engine) as s:
            s.execute(
                self.intake_model.__table__.delete().where(
                    self.intake_model.__table__.c.internal_record_id == record_id
                )
            )
            s.execute(
                self.intake_model.__table__.insert().values(
                    internal_record_id=record_id,
                    submission_id=submission_id,
                    first_name="Abebe",
                    created_by="test",
                    created_at=now,
                    last_approved_at=now,
                    last_approved_by="test",
                    **{FIELD: "doc-123"},
                )
            )
            s.commit()
            got = (
                s.execute(
                    self.intake_model.__table__.select().where(
                        self.intake_model.__table__.c.internal_record_id == record_id
                    )
                )
                .mappings()
                .one()
            )
        self.assertEqual(got[FIELD], "doc-123", "photo id did not survive a real DB round trip")


if __name__ == "__main__":
    unittest.main(verbosity=2)
