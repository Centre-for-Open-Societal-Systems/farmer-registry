"""Intake submission reads resolve the farmer photo into a presigned URL.

Same convention as test_farmer_photo_upload.py: imports openg2p_registry_core,
so it runs in the container, not on a bare host checkout.

The platform serializes intake rows with _serialize_model, which emits mapped
columns only. record_image_url is not a column -- it is a presigned URL added
at read time -- so without this the photo captured at intake comes back as a
bare document_id, and the approval screen
(/tasks/intake-form/<register>/<submission_id>), which renders the same intake
sections, has nothing for the header-section widget's imageUrl to draw.

The document store itself is stubbed here; these tests assert the resolution
contract and the install mechanics.
"""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from openg2p_registry_core.services import G2PIntakeFormDataService

from openg2p_registry_farmer_extension.register_domain.services import (
    g2p_intake_form_data_service as service_module,
)
from openg2p_registry_farmer_extension.register_domain.services.g2p_intake_form_data_service import (
    SECTION_PAYLOAD_READERS,
    attach_record_image_urls,
    install_record_image_url_resolution,
)

DOC_ID = "doc-abc"
URL = "https://minio.localtest.me/documents/abc?sig=x"


def _section(*records):
    return SimpleNamespace(records=list(records))


def _stub_document_service(urls):
    document_service = MagicMock()
    document_service.get_document_urls = AsyncMock(return_value=urls)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return document_service, session_cm


def _patched(document_service, session_cm):
    return (
        patch.object(
            service_module.G2PDocumentService,
            "get_component",
            return_value=document_service,
        ),
        patch.object(service_module, "async_sessionmaker", return_value=lambda: session_cm),
        patch.object(service_module, "dbengine", MagicMock()),
    )


def _run(section_payloads, urls=None):
    """Drive the resolver with the document lookup and session stubbed."""
    document_service, session_cm = _stub_document_service(
        {DOC_ID: URL} if urls is None else urls
    )
    first, second, third = _patched(document_service, session_cm)
    with first, second, third:
        asyncio.run(attach_record_image_urls(section_payloads))
    return document_service.get_document_urls


class TestAttachRecordImageUrls(unittest.TestCase):
    def test_photo_record_gains_a_presigned_url(self):
        record = {"record_image_document_id": DOC_ID, "first_name": "Abebe"}
        _run([_section(record)])
        self.assertEqual(record["record_image_url"], URL)

    def test_records_without_a_photo_are_untouched(self):
        record = {"first_name": "Abebe"}
        lookup = _run([_section(record)])
        lookup.assert_not_awaited()
        self.assertEqual(record, {"first_name": "Abebe"})

    def test_ids_are_resolved_in_one_batched_lookup(self):
        """One submission read must not fan out into a query per photo."""
        records = [{"record_image_document_id": f"doc-{i}"} for i in range(3)]
        lookup = _run(
            [_section(records[0]), _section(*records[1:])],
            urls={f"doc-{i}": f"{URL}&i={i}" for i in range(3)},
        )
        lookup.assert_awaited_once()
        self.assertEqual(sorted(lookup.await_args.args[1]), ["doc-0", "doc-1", "doc-2"])
        for index, record in enumerate(records):
            self.assertEqual(record["record_image_url"], f"{URL}&i={index}")

    def test_unknown_document_id_leaves_the_key_absent(self):
        """get_document_urls skips ids it cannot find. Writing None over the
        key would hand the widget an explicit empty image instead of nothing."""
        record = {"record_image_document_id": "doc-missing"}
        _run([_section(record)], urls={})
        self.assertNotIn("record_image_url", record)

    def test_lookup_failure_does_not_fail_the_read(self):
        """A submission that cannot show its photo is still worth showing."""
        record = {"record_image_document_id": DOC_ID}
        document_service = MagicMock()
        document_service.get_document_urls = AsyncMock(
            side_effect=RuntimeError("minio down")
        )
        lookup = patch.object(
            service_module.G2PDocumentService,
            "get_component",
            return_value=document_service,
        )
        engine = patch.object(service_module, "dbengine", MagicMock())
        with lookup, engine:
            asyncio.run(attach_record_image_urls([_section(record)]))
        self.assertNotIn("record_image_url", record)

    def test_empty_and_none_payloads_are_safe(self):
        for payloads in (None, [], [_section()]):
            with self.subTest(payloads=payloads):
                asyncio.run(attach_record_image_urls(payloads))


class TestInstall(unittest.TestCase):
    """The install patches the platform CLASS. These tests restore it."""

    def setUp(self):
        self._originals = {
            name: getattr(G2PIntakeFormDataService, name)
            for name in SECTION_PAYLOAD_READERS
        }

    def tearDown(self):
        for name, reader in self._originals.items():
            setattr(G2PIntakeFormDataService, name, reader)

    def test_every_section_payload_reader_is_wrapped(self):
        install_record_image_url_resolution()
        for name in SECTION_PAYLOAD_READERS:
            with self.subTest(reader=name):
                self.assertIsNot(
                    getattr(G2PIntakeFormDataService, name),
                    self._originals[name],
                    f"{name} was not wrapped; its payloads keep the bare document id",
                )

    def test_the_named_readers_exist_on_the_pinned_platform(self):
        """A rename upstream must fail loudly at startup, not degrade into a
        photo that quietly stops appearing."""
        for name in SECTION_PAYLOAD_READERS:
            with self.subTest(reader=name):
                self.assertTrue(hasattr(G2PIntakeFormDataService, name))

    def test_missing_reader_raises(self):
        for name in SECTION_PAYLOAD_READERS:
            delattr(G2PIntakeFormDataService, name)
        with self.assertRaises(AttributeError):
            install_record_image_url_resolution()

    def test_install_is_idempotent(self):
        """The extension Initializer can run more than once per process;
        re-wrapping would nest the resolution once per call."""
        install_record_image_url_resolution()
        wrapped = {
            name: getattr(G2PIntakeFormDataService, name)
            for name in SECTION_PAYLOAD_READERS
        }
        install_record_image_url_resolution()
        for name in SECTION_PAYLOAD_READERS:
            with self.subTest(reader=name):
                self.assertIs(getattr(G2PIntakeFormDataService, name), wrapped[name])

    def test_wrapper_resolves_both_return_shapes(self):
        """get_tab_records returns the section payload list directly; the other
        two wrap it in a SubmissionResponsePayload."""
        record_a = {"record_image_document_id": DOC_ID}
        record_b = {"record_image_document_id": DOC_ID}

        # Plain async functions, not AsyncMock: a mock auto-creates any
        # attribute asked of it, so the install's "already wrapped" marker
        # check would read as truthy and skip wrapping the stub entirely.
        for name, returned in (
            ("get_tab_records", [_section(record_a)]),
            (
                "get_intake_form_submission",
                SimpleNamespace(section_payloads=[_section(record_b)]),
            ),
        ):
            async def reader(*_args, _returned=returned, **_kwargs):
                return _returned

            setattr(G2PIntakeFormDataService, name, reader)
        install_record_image_url_resolution()

        document_service, session_cm = _stub_document_service({DOC_ID: URL})
        first, second, third = _patched(document_service, session_cm)
        with first, second, third:
            asyncio.run(G2PIntakeFormDataService.get_tab_records("s", "t"))
            asyncio.run(G2PIntakeFormDataService.get_intake_form_submission("s"))

        self.assertEqual(record_a["record_image_url"], URL)
        self.assertEqual(record_b["record_image_url"], URL)


class TestSubclassWouldNotWin(unittest.TestCase):
    def test_component_lookup_returns_the_first_registered_instance(self):
        """Why this is a class patch and not a subclass. The staff-api
        entrypoint constructs CoreInitializer() -- which builds the platform's
        own instance -- before ExtensionsInitializer(), so a subclass
        registered from this extension always lands second, and
        BaseComponent.get_component returns the first isinstance match. If this
        ever stops holding, the simpler subclass override becomes available."""
        from openg2p_fastapi_common.service import BaseService

        class Core(BaseService):
            pass

        class Ext(Core):
            pass

        first, _second = Core(), Ext()
        self.assertIs(Core.get_component(), first)


if __name__ == "__main__":
    unittest.main()
