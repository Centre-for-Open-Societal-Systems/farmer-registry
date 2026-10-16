"""Retain upstream polling/checkpoints and transfer referenced ODK attachments.

A missing or failed attachment aborts the record before Registry intake and
checkpoint advancement. Retrying uses the unchanged upstream source event ID.
"""
import base64
import mimetypes
from urllib.parse import quote

import httpx

from openg2p_connector_service.auth import get_auth_strategy
from openg2p_connector_service.transports.odk_central import OdkCentralTransport, _cfg_bool
from openg2p_connector_service.transports.registry import register_transport


class AttachmentTransferError(RuntimeError):
    pass


class AttachmentListingMissing(AttachmentTransferError):
    pass


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def replace_files(value, files):
    if isinstance(value, dict):
        for key, item in value.items():
            value[key] = dict(files[item]) if isinstance(item, str) and item in files else replace_files(item, files)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            value[index] = dict(files[item]) if isinstance(item, str) and item in files else replace_files(item, files)
    return value


async def embed(client, root, headers, entry, max_bytes):
    response = await client.get(root, headers=headers)
    if response.status_code == 404:
        raise AttachmentListingMissing("ODK attachment listing is unavailable")
    response.raise_for_status()
    attachments = response.json()
    if not isinstance(attachments, list):
        raise AttachmentTransferError("Invalid ODK attachment listing")
    referenced = set(strings(entry))
    files = {}
    for attachment in attachments:
        name = attachment.get("name")
        if not name or name not in referenced:
            continue
        if name in (".", ".."):
            raise AttachmentTransferError("Invalid ODK attachment name")
        if attachment.get("exists") is False:
            raise AttachmentTransferError("Referenced ODK attachment has not been uploaded")
        content = bytearray()
        async with client.stream("GET", root + "/" + quote(name, safe=""), headers=headers) as download:
            download.raise_for_status()
            length = download.headers.get("content-length")
            if length and int(length) > max_bytes:
                raise AttachmentTransferError("ODK attachment exceeds configured size limit")
            async for chunk in download.aiter_bytes():
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise AttachmentTransferError("ODK attachment exceeds configured size limit")
            mime = download.headers.get("content-type", "").split(";", 1)[0].strip() or mimetypes.guess_type(name)[0] or "application/octet-stream"
        files[name] = {"__type": "File", "name": name, "type": mime,
                       "data": base64.b64encode(content).decode("ascii")}
    replace_files(entry, files)


@register_transport("odk_central")
class FarmerOdkTransport(OdkCentralTransport):
    async def fetch(self, connector):
        cfg = connector.get_source_config()
        if not _cfg_bool(cfg, "embed_attachments", default=True):
            raise AttachmentTransferError("Farmer ODK pipelines require attachment transfer")
        maximum = int(cfg.get("attachment_max_bytes", 10 * 1024 * 1024))
        if not 0 < maximum <= 50 * 1024 * 1024:
            raise AttachmentTransferError("Invalid attachment size limit")
        context = await get_auth_strategy(connector.auth_type).get_auth_context(connector)
        base = (context.base_url or self._resolve_base_url(cfg)).rstrip("/")
        form = quote(str(cfg["form_id"]), safe="")
        root = f"{base}/v1/projects/{cfg['project_id']}/forms/{form}"
        async with httpx.AsyncClient(timeout=60) as client:
            async for record in super().fetch(connector):
                instance = record.data.get("__id")
                if not instance:
                    raise AttachmentTransferError("ODK record has no stable submission ID")
                suffix = "/submissions/" + quote(str(instance), safe="") + "/attachments"
                draft = _cfg_bool(cfg, "use_draft", default=False)
                try:
                    await embed(client, root + ("/draft" if draft else "") + suffix,
                                dict(context.headers), record.data, maximum)
                except AttachmentListingMissing:
                    # Only a missing draft listing permits published fallback.
                    # A missing file must never substitute bytes from another
                    # draft/published submission with the same identifier.
                    if not draft or not _cfg_bool(cfg, "draft_odata_fallback_on_404", default=True):
                        raise
                    await embed(client, root + suffix, dict(context.headers), record.data, maximum)
                yield record
