"""Composition check: browser patch output -> farmer server-side normalizer.

There are TWO mechanisms that can put a photo on a farmer record, and they meet
inside the same save:

  * the browser patch this branch ships, which uploads change.image and stamps
    record_image_document_id with the returned document_id; and
  * G2PRegisterDomainServiceFarmer._persist_embedded_profile_photo, which
    catches a photo that arrives still EMBEDDED (base64) and uploads it
    server-side.

If those two disagree the fix is worse than the bug: a double upload (two
catalog rows and a leaked object for one photo), or the normalizer overwriting
the id the browser just stamped, or the id being dropped for not looking like an
embedded file. None of that is visible from either side alone, and neither the
browser suite nor the persistence suite covers it -- they each stop at this
boundary.

What the browser patch actually emits, per the shipped bundle:
  * record_image_document_id = "<document_id>"   (a plain string)
  * record_image_url         = ""                (the widget library blanks the
                                                  field when it lifts the File
                                                  out into change.image)

so this asserts the real normalizer leaves that combination alone.

Runs in the staff-api image (needs openg2p_registry_farmer_extension).
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from openg2p_registry_farmer_extension.register_domain.services import (
    g2p_register_domain_service_farmer as farmer_module,
)
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_farmer import (
    G2PRegisterDomainServiceFarmer,
)

# Exactly what the patched bundle produces for a section whose photo was picked.
BROWSER_PATCH_OUTPUT = {
    "record_image_document_id": "doc-123",
    "record_image_url": "",
    "first_name": "Abebe",
    "created_by": "staff",
}


class TestBrowserPatchComposesWithServerNormalizer(unittest.TestCase):
    def _run(self, record):
        with patch.object(
            farmer_module, "upload_embedded_file", new=AsyncMock(return_value="server-doc")
        ) as upload:
            asyncio.run(
                G2PRegisterDomainServiceFarmer._persist_embedded_profile_photo(record)
            )
        return upload

    def test_stamped_document_id_is_not_re_uploaded(self):
        """The browser already uploaded. A second upload here would create a
        duplicate catalog row and orphan an object for a single photo."""
        record = dict(BROWSER_PATCH_OUTPUT)
        upload = self._run(record)
        upload.assert_not_awaited()

    def test_stamped_document_id_survives_normalization(self):
        """The id the browser stamped must be the id that gets persisted."""
        record = dict(BROWSER_PATCH_OUTPUT)
        self._run(record)
        self.assertEqual(record["record_image_document_id"], "doc-123")

    def test_blanked_record_image_url_never_reaches_the_insert(self):
        """record_image_url is server-computed on read and is NOT a column;
        leaving it in the record would break the insert."""
        record = dict(BROWSER_PATCH_OUTPUT)
        self._run(record)
        self.assertNotIn("record_image_url", record)

    def test_unrelated_fields_untouched(self):
        record = dict(BROWSER_PATCH_OUTPUT)
        self._run(record)
        self.assertEqual(record["first_name"], "Abebe")

    def test_fallback_still_works_for_a_still_embedded_photo(self):
        """The server-side path must keep working for any client that does NOT
        carry the browser patch (a direct API caller, or an older cached
        bundle) -- otherwise this branch would narrow existing behaviour."""
        record = {
            "record_image_url": {
                "__type": "File",
                "name": "photo.jpg",
                "type": "image/jpeg",
                "data": "aGk=",
            },
            "created_by": "staff",
        }
        upload = self._run(record)
        upload.assert_awaited_once()
        self.assertEqual(record["record_image_document_id"], "server-doc")


if __name__ == "__main__":
    unittest.main(verbosity=2)
