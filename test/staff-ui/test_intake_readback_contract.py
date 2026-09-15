"""Characterisation of the intake read-back path for the farmer photo.

Scope note. The reported bug was that a photo taken during intake never reached
the server; that is what this branch fixes and what the other suites verify.
This file pins the READ side, which is adjacent and easy to confuse with it, so
the distinction is recorded as executable fact rather than an opinion in a
review comment.

Two different read paths exist and they behave differently:

  * REGISTER detail view -- G2PRegisterHierarchicalService._convert_records_to_record_data
    batch-resolves record_image_document_id into a presigned `record_image_url`
    and injects it as an extra field. The header widget reads that, which is why
    an intake photo shows up on the farmer's detail view after approval.
  * INTAKE form -- G2PIntakeFormDataService._serialize_model returns ONLY real
    mapped columns. record_image_url is not a column, so it is not present, and
    the intake form has no presigned URL to render.

So: the photo is stored correctly and displays on the detail view, but the
intake form itself does not re-render it from the server on a later visit. That
is pre-existing platform behaviour, not something this branch introduced or
regressed -- and it is deliberately NOT "fixed" here, because doing so would
mean changing a shared platform service well outside the reported defect.

These assertions are characterisation tests: if a future platform version starts
resolving record_image_url on the intake path, the last test fails and tells
whoever is reading that this note is stale.
"""

import unittest

FIELD = "record_image_document_id"
URL_FIELD = "record_image_url"


class TestIntakeReadBackContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from openg2p_registry_farmer_extension.register_domain.models.farmer import (
            G2PIntakeFormFarmer,
        )

        cls.intake_model = G2PIntakeFormFarmer

    def test_document_id_is_a_real_column_and_reads_back(self):
        """The stored id itself IS returned by the intake read path, so the
        record keeps its photo reference across saves."""
        from openg2p_registry_core.services.intake_form_data_service import (
            G2PIntakeFormDataService,
        )

        # A real (unattached) ORM instance, so _serialize_model walks the
        # genuine mapper rather than a stand-in.
        row = self.intake_model()
        setattr(row, FIELD, "doc-123")
        setattr(row, "internal_record_id", "rec-1")

        service = G2PIntakeFormDataService()
        serialized = service._serialize_model(row, {"submission_id", "section_id"})

        self.assertIn(FIELD, serialized, "intake read-back lost the photo reference")
        self.assertEqual(serialized[FIELD], "doc-123")
        self.assertNotIn(
            URL_FIELD, serialized, "intake payload unexpectedly carries a presigned URL"
        )

    def test_record_image_url_is_not_a_column(self):
        """It is server-computed on read, which is why the farmer normalizer
        must strip it before an insert."""
        columns = {c.name for c in self.intake_model.__table__.columns}
        self.assertNotIn(
            URL_FIELD,
            columns,
            "record_image_url became a real column; the save-path normalizer "
            "that pops it should be revisited",
        )

    def test_intake_read_path_does_not_resolve_a_presigned_url(self):
        """Characterisation: the intake payload carries the id but no URL,
        while the REGISTER path does resolve one. Asserting both halves means
        this cannot silently become a false statement about either service.

        If the intake half ever fails, the platform has started resolving
        record_image_url there -- which would be an improvement, and would make
        the docstring above wrong. Update it rather than forcing this green.
        """
        import inspect as pyinspect

        from openg2p_registry_core.services.g2p_register_hierarchical_service import (
            G2PRegisterHierarchicalService,
        )
        from openg2p_registry_core.services.intake_form_data_service import (
            G2PIntakeFormDataService,
        )

        intake_src = pyinspect.getsource(G2PIntakeFormDataService)
        register_src = pyinspect.getsource(G2PRegisterHierarchicalService)

        self.assertNotIn(
            "get_document_urls",
            intake_src,
            "intake service now resolves presigned URLs; refresh this note",
        )
        self.assertIn(
            "get_document_urls",
            register_src,
            "register service no longer resolves presigned URLs -- the detail "
            "view would stop showing the farmer photo",
        )
        self.assertIn(
            URL_FIELD,
            register_src,
            f"register service no longer injects {URL_FIELD}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
