"""The Partner API's ingest, with ODK signature checks and once-only events.

An ODK envelope must be signed by its partner's active Partner Management key
(signature.py). The connector retries a submission until the registry answers,
so each partner's ODK message id is accepted once: a retry gets the first
ingest's correlation id back, and a reused id with different data is refused.
Other data models are ingested exactly as the platform does.
"""
import contextvars
import logging

from fastapi import HTTPException
from openg2p_fastapi_common.context import component_registry, get_async_session_maker
from openg2p_registry_core.errors import G2PRegistryErrorCodes, G2PRegistryException
from openg2p_registry_core.helpers.partner_management import get_partner_mgmt_settings
from openg2p_registry_core.models import IncomingRawData, IncomingRawDataPayload
from openg2p_registry_core.services.g2p_ingest_service import G2PIngestService
from sqlalchemy import func, select

from . import ODK_DATA_MODEL
from .signature import InvalidOdkSignature, verify_odk_signature

_logger = logging.getLogger("g2p-partner-service")

# The verified partner match of the envelope being ingested, so the platform's
# own ingest reuses it instead of asking Partner Management and verifying again.
_matched = contextvars.ContextVar("oan_odk_matched", default=None)


class OANIngestService(G2PIngestService):
    async def ingest_data(self, data_model_mnemonic, ingest_data, *, register_id=None, intake_form_id=None):
        async with get_async_session_maker()() as session:
            data_model = await self._get_data_model(ingest_data, data_model_mnemonic, session)
            if data_model.data_model_id != ODK_DATA_MODEL:
                return await super().ingest_data(data_model_mnemonic, ingest_data,
                                                 register_id=register_id, intake_form_id=intake_form_id)
            matched = await self._match_model_signature_pattern(data_model.data_model_id, ingest_data, session)
            partner, _, _, key_path = matched
            message_id = self._match_message_id_pattern(ingest_data, key_path)
            if not isinstance(message_id, str) or not message_id:
                raise G2PRegistryException(
                    code=G2PRegistryErrorCodes.INVALID_REQUEST.value[1],
                    message="ODK message: header.message_id is required; the connector sets it per submission",
                )
            lock = (func.hashtext("farmer-odk:" + partner.partner_id), func.hashtext(message_id))
            # A session lock, held across the platform's own transaction below.
            await session.execute(select(func.pg_advisory_lock(*lock)))
            try:
                first = await self._first_ingest(session, partner.partner_id, data_model.data_model_id, message_id)
                if first is not None:
                    stored = await session.get(IncomingRawDataPayload, first.ingest_id)
                    if _message(stored.raw_data_json) != _message(ingest_data):
                        raise G2PRegistryException(
                            code=G2PRegistryErrorCodes.INVALID_REQUEST.value[1],
                            message=(f"ODK message {message_id} was already received with different data. "
                                     "The connector must send a new message id for a changed submission"),
                        )
                    _logger.info("ODK message %s from %s already ingested; returning its correlation id",
                                 message_id, partner.partner_id)
                    return first.ingest_correlation_id, await self._response_store_id(session, data_model)
                token = _matched.set(matched)
                try:
                    return await super().ingest_data(data_model_mnemonic, ingest_data,
                                                     register_id=register_id, intake_form_id=intake_form_id)
                finally:
                    _matched.reset(token)
            finally:
                await session.execute(select(func.pg_advisory_unlock(*lock)))

    async def _match_model_signature_pattern(self, data_model_id, ingest_data, session):
        cached = _matched.get()
        if cached is not None:
            return cached
        matched = await super()._match_model_signature_pattern(data_model_id, ingest_data, session)
        if data_model_id == ODK_DATA_MODEL:
            partner, signature, signature_payload, _ = matched
            try:
                await verify_odk_signature(partner.partner_id, signature, signature_payload, ingest_data,
                                           get_partner_mgmt_settings().partner_mgmt_api_url)
            except InvalidOdkSignature as error:
                raise HTTPException(status_code=401, detail=str(error)) from None
        return matched

    @staticmethod
    async def _first_ingest(session, partner_id, data_model_id, message_id):
        result = await session.execute(
            select(IncomingRawData)
            .where(IncomingRawData.partner_id == partner_id,
                   IncomingRawData.data_model_id == data_model_id,
                   IncomingRawData.ingest_message_id == message_id)
            .order_by(IncomingRawData.receipt_date_time)
            .limit(1))
        return result.scalar_one_or_none()

    @staticmethod
    async def _response_store_id(session, data_model):
        if not data_model.response_template_document_id:
            return None
        from openg2p_registry_core.services.g2p_template_service import (
            G2PTemplateService,
        )

        return await G2PTemplateService.get_component().resolve_template_store_id(
            session, data_model.response_template_document_id)


def _message(envelope):
    body = envelope.get("body") if isinstance(envelope, dict) else None
    return body.get("message") if isinstance(body, dict) else None


def install() -> OANIngestService:
    """Put the service ahead of core's: the ingest controller looks it up per request."""
    current = G2PIngestService.get_component()
    if isinstance(current, OANIngestService):
        return current
    service = OANIngestService()
    component_registry.remove(service)
    index = component_registry.index(current) if current in component_registry else len(component_registry)
    component_registry.insert(index, service)
    return service
