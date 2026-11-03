"""The farmer photo inside the DCI farmer_reference block.

Crop Sown and Livestock keep their own copy of the farmer's photo. A document
id or a presigned link of this registry means nothing to them (and a link
expires), so the signed, consent-checked DCI response carries the photo's
bytes: ``{"content_type", "sha256", "data"}`` with ``data`` in base64. The
receivers store it in their own document store and skip it when ``sha256`` is
the photo they already hold.

The DCI service renders its output template synchronously. The partner search
it renders from (core ``PartnerRegisterSearch``) returns plain table columns, so
a record names its photo only by ``record_image_document_id``. Before the
render, ``add_record_image_urls`` gives each such record the
``record_image_url`` the staff search would (a presigned URL of the documents
bucket, from core ``G2PDocumentService.get_document_urls``). The function reads
the object named in that URL straight from the document store, the same
synchronous storage call the template helper itself makes, so no request goes
out to the public storage host.

A missing photo, an object outside the documents bucket, an unreadable object
or one over the size limit renders as ``null``: the farmer's other details
still reach the receivers.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from urllib.parse import unquote, urlsplit

_logger = logging.getLogger(__name__)

# A template global, not a filter: a template naming an unknown filter fails
# to compile, while an unknown global is only undefined, so the response still
# renders (without the photo) in a process that has not installed it.
FUNCTION_NAME = "farmer_photo"
DOCUMENTS_BUCKET = "documents"
# The photo widget keeps photos under 2 MB (10_sections.sql, maxSizeKb 2048).
MAX_PHOTO_BYTES = 2 * 1024 * 1024
_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),
)


def photo_object(url: object) -> tuple[str, str] | None:
    """The (bucket, object name) a presigned path-style URL names, or None."""
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        path = urlsplit(url.strip()).path
    except ValueError:
        return None
    parts = [unquote(part) for part in path.split("/") if part]
    if len(parts) < 2:
        return None
    return parts[0], "/".join(parts[1:])


def content_type(data: bytes) -> str | None:
    for signature, kind in _SIGNATURES:
        if data.startswith(signature):
            if kind == "image/webp" and data[8:12] != b"WEBP":
                continue
            return kind
    return None


def encode_photo(data: bytes) -> dict | None:
    if not data or len(data) > MAX_PHOTO_BYTES:
        return None
    kind = content_type(data)
    if kind is None:
        return None
    return {"content_type": kind, "sha256": hashlib.sha256(data).hexdigest(),
            "data": base64.b64encode(data).decode("ascii")}


def make_photo_function(download):
    """A template function: presigned photo URL -> photo object (or None).

    ``download(object_name, bucket)`` returns the stored bytes.
    """

    def farmer_photo(url):
        target = photo_object(url)
        if target is None:
            return None
        bucket, name = target
        if bucket != DOCUMENTS_BUCKET:
            return None
        try:
            data = download(name, bucket)
        except Exception:  # noqa: BLE001 - a missing photo must not fail the lookup
            _logger.warning("Farmer photo could not be read from the document store")
            return None
        return encode_photo(data)

    return farmer_photo


def records_missing_image_url(pages) -> list[dict]:
    """Search records that name a photo document but carry no image URL."""
    return [record for page in pages for record in (getattr(page, "records", None) or [])
            if isinstance(record, dict) and record.get("record_image_document_id")
            and not record.get("record_image_url")]


def add_record_image_urls(records, urls: dict) -> None:
    """Set ``record_image_url`` from ``{document_id: presigned URL}``; unknown ids stay as they are."""
    for record in records:
        url = urls.get(record["record_image_document_id"])
        if url:
            record["record_image_url"] = url


def install_search_image_urls():
    """Resolve the photo URLs of the partner search results before the render.

    Wraps the DCI service's search step in this process (the partner API); the
    platform files stay unchanged. A failure leaves the URLs out, so the
    response renders without the photo rather than failing.
    """
    try:
        from openg2p_fastapi_common.context import get_async_session_maker
        from openg2p_registry_core.services.g2p_document_service import (
            G2PDocumentService,
        )
        from openg2p_registry_partner_api.search.dci.services.g2p_dci_service import (
            G2PDciService,
        )
    except ImportError:
        return None
    search = G2PDciService._run_search
    if getattr(search, "resolves_record_image_urls", False):
        return G2PDciService

    async def _run_search(self, searches, allowed_columns):
        pages = await search(self, searches, allowed_columns)
        records = records_missing_image_url(pages)
        if records:
            try:
                async with get_async_session_maker()() as session:
                    urls = await G2PDocumentService.get_component().get_document_urls(
                        session, [record["record_image_document_id"] for record in records])
            except Exception:  # noqa: BLE001 - a missing photo must not fail the lookup
                _logger.warning("Farmer photo URLs could not be resolved for the DCI search")
                urls = {}
            add_record_image_urls(records, urls)
        return pages

    _run_search.resolves_record_image_urls = True
    G2PDciService._run_search = _run_search
    return G2PDciService


def install_dci_photo():
    """Register the function on the template helper of this process.

    The partner API renders the DCI response with the core TemplateHelper,
    created before the extension initializes; other processes have one too and
    simply never use it.
    """
    install_search_image_urls()
    try:
        from openg2p_registry_core.helpers import TemplateHelper
        from openg2p_registry_core.helpers.document import get_document_handler
        from openg2p_registry_core.models.enum import DocumentBucket
    except ImportError:
        return None
    helper = TemplateHelper.get_component()
    if helper is None:
        return None

    def download(name, bucket):
        return get_document_handler().download(name, DocumentBucket(bucket))

    helper.env.globals[FUNCTION_NAME] = make_photo_function(download)
    return helper
