"""Normalization of embedded profile photos on save (farmer intake photo capture).

Same convention as test_intake_server_validation.py: imports openg2p_registry_core,
so it runs in the container, not on a bare host checkout.

The photo reaches _persist_embedded_profile_photo by one of two routes:

- the header-section widget's picker, which writes the embedded file into
  record_image_url (not a real column -- it only exists as a presigned URL on
  read). Both entry points use it: the register detail view's header and the
  intake form's photo section (zz_farmer_photo_section.sql), which reuses that
  widget for its avatar picker.
- a 'file' widget bound straight to record_image_document_id, where the base64
  blob would otherwise be persisted verbatim into a text column. The intake
  photo section was built that way first; the branch stays because it is the
  shape any future plain-file photo binding would take.

One field, one stored document_id, so a photo captured at intake is the same
profile picture the detail view's header renders.

The upload itself (MinIO + G2PRegistryDocument catalog row) is the platform's
upload_embedded_file, exercised elsewhere; here it is stubbed so these tests
assert only the routing/normalization contract.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from openg2p_registry_farmer_extension.register_domain.services import (
    g2p_register_domain_service_farmer as farmer_service_module,
)
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_farmer import (
    G2PRegisterDomainServiceFarmer,
)

EMBEDDED = {"__type": "File", "name": "photo.jpg", "type": "image/jpeg", "data": "aGk="}


class TestEmbeddedProfilePhotoPersistence(unittest.TestCase):
    def setUp(self):
        self.persist = G2PRegisterDomainServiceFarmer._persist_embedded_profile_photo

    def _run(self, record):
        with patch.object(
            farmer_service_module,
            "upload_embedded_file",
            new=AsyncMock(return_value="doc-123"),
        ) as upload:
            asyncio.run(self.persist(record))
        return upload

    def test_header_picker_value_in_record_image_url_is_uploaded(self):
        record = {"record_image_url": dict(EMBEDDED), "created_by": "staff"}
        upload = self._run(record)
        upload.assert_awaited_once()
        self.assertEqual(record["record_image_document_id"], "doc-123")
        # record_image_url is not a real column and must never reach the insert
        self.assertNotIn("record_image_url", record)

    def test_plain_file_widget_value_in_document_id_is_uploaded(self):
        record = {"record_image_document_id": dict(EMBEDDED), "created_by": "staff"}
        upload = self._run(record)
        upload.assert_awaited_once()
        self.assertEqual(record["record_image_document_id"], "doc-123")

    def test_existing_document_id_string_passes_through(self):
        record = {"record_image_document_id": "already-a-document-id"}
        upload = self._run(record)
        upload.assert_not_awaited()
        self.assertEqual(record["record_image_document_id"], "already-a-document-id")

    def test_presigned_url_string_is_dropped_without_upload(self):
        """On an untouched edit the widget echoes back the read-time presigned
        URL string; that is not a fresh pick and must not clobber the stored
        document_id -- but it still must not reach the insert."""
        record = {
            "record_image_url": "https://minio.localtest.me/documents/abc?sig=x",
            "record_image_document_id": "existing-doc",
        }
        upload = self._run(record)
        upload.assert_not_awaited()
        self.assertNotIn("record_image_url", record)
        self.assertEqual(record["record_image_document_id"], "existing-doc")

    def test_record_without_photo_keys_is_untouched(self):
        record = {"first_name": "Abebe"}
        upload = self._run(record)
        upload.assert_not_awaited()
        self.assertEqual(record, {"first_name": "Abebe"})


if __name__ == "__main__":
    unittest.main()
