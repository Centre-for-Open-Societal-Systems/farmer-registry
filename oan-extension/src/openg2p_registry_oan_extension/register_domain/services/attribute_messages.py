"""Only wording around the native code-list validator; its rules stay in core."""

import httpx
from openg2p_fastapi_common.context import component_registry
from openg2p_registry_core.errors import G2PRegistryErrorCodes, G2PRegistryException
from openg2p_registry_core.services.g2p_attribute_value_validator import (
    G2PAttributeValueValidator,
)

from .upstream_messages import MDS_UNAVAILABLE, reword


async def _messages():
    from . import _load

    return (await _load())[2]


class OANAttributeValueValidator(G2PAttributeValueValidator):
    async def validate_records(self, records, *, field_map=None):
        try:
            return await super().validate_records(records, field_map=field_map)
        except G2PRegistryException as error:
            if error.code != G2PRegistryErrorCodes.REQUEST_VALIDATION_ERROR.value[1]:
                raise
            message = reword(error.message or "", await _messages())
            raise G2PRegistryException(code=error.code, message=message) from error
        except (httpx.HTTPError, RuntimeError) as error:
            # Native MDS transport/configuration errors also fail closed, with
            # an actionable service message rather than a generic system error.
            messages = await _messages()
            message = messages.get("oan_up_mds_unavailable") or MDS_UNAVAILABLE
            raise G2PRegistryException(
                code=G2PRegistryErrorCodes.REQUEST_VALIDATION_ERROR.value[1],
                message=message,
            ) from error


def install_attribute_messages():
    core = G2PAttributeValueValidator.get_component()
    if isinstance(core, OANAttributeValueValidator):
        return core
    service = OANAttributeValueValidator()
    component_registry.remove(service)
    first = next(
        (
            i
            for i, component in enumerate(component_registry)
            if isinstance(component, G2PAttributeValueValidator)
        ),
        len(component_registry),
    )
    component_registry.insert(first, service)
    return service
