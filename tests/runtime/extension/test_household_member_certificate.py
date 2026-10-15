"""A household member's land certificate (intake 'file' widget / ODK connector).

Same convention as test_farmer_photo_upload.py: imports openg2p_registry_core,
so it runs in the container. The upload (and its type/size profile) is the
platform's upload_embedded_file, stubbed here; these tests pin the routing:
an embedded file becomes a document_id, the flag follows it, and an existing
document_id or an empty value passes through.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from openg2p_registry_farmer_extension.register_domain.services import (
    g2p_register_domain_service_household_member as member_module,
)
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_household_member import (
    G2PRegisterDomainServiceHouseholdMember,
)

EMBEDDED = {"__type": "File", "name": "deed.pdf", "type": "application/pdf", "data": "aGk="}


class TestMemberCertificate(unittest.TestCase):
    def _validate(self, record, upload=None):
        stub = upload or AsyncMock(return_value="doc-123")
        with patch.object(member_module, "upload_embedded_file", new=stub):
            asyncio.run(G2PRegisterDomainServiceHouseholdMember().validate_domain_attributes([record]))
        return stub

    def test_embedded_file_is_uploaded_and_replaced_by_its_document_id(self):
        record = {"first_name": "Abebe", "certificate_storage_id": dict(EMBEDDED), "created_by": "staff"}
        upload = self._validate(record)
        upload.assert_awaited_once_with(EMBEDDED, "staff", purpose="member_certificate")
        self.assertEqual(record["certificate_storage_id"], "doc-123")
        self.assertTrue(record["certificate_provided"])

    def test_existing_document_id_passes_through_without_an_upload(self):
        record = {"certificate_storage_id": "doc-old"}
        upload = self._validate(record)
        upload.assert_not_awaited()
        self.assertEqual(record["certificate_storage_id"], "doc-old")
        self.assertTrue(record["certificate_provided"])

    def test_no_certificate_means_not_provided(self):
        for value in (None, "", "  "):
            record = {"certificate_storage_id": value}
            self._validate(record)
            self.assertFalse(record["certificate_provided"])

    def test_a_refused_file_refuses_the_save(self):
        # upload_embedded_file raises through validation_error() on a type or
        # size the document profile rejects; nothing is saved without it.
        upload = AsyncMock(side_effect=ValueError("file type not allowed"))
        with self.assertRaises(ValueError):
            self._validate({"certificate_storage_id": dict(EMBEDDED)}, upload)


if __name__ == "__main__":
    unittest.main()
