"""The registered wrapper changes wording while native core still validates."""

import asyncio
from typing import ClassVar

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("openg2p_registry_core")

from openg2p_registry_core.errors import G2PRegistryException

from openg2p_registry_farmer_extension.register_domain.services import (
    attribute_messages as am,
)
from openg2p_registry_farmer_extension.register_domain.services.upstream_messages import (
    MDS_UNAVAILABLE,
)


class NativeValidatorWithFixtureLists(am.AttributeValueValidator):
    codes: ClassVar[dict[str, set[str]]] = {"GENDER": {"MALE"}}

    @property
    def enabled(self):
        return True

    async def _load(self):
        return self.codes


def messages(monkeypatch):
    async def load():
        return {"gender": "Gender"}

    monkeypatch.setattr(am, "_messages", load)


def test_native_validator_success_and_reworded_rejection(monkeypatch):
    messages(monkeypatch)
    validator = NativeValidatorWithFixtureLists()

    async def run():
        await validator.validate_records(
            [{"gender": "MALE"}], field_map={"gender": "GENDER"}
        )
        with pytest.raises(G2PRegistryException) as error:
            await validator.validate_records(
                [{"gender": "unknown"}], field_map={"gender": "GENDER"}
            )
        assert (
            error.value.message
            == 'Gender: "unknown" is not one of the choices. Pick one from the list.'
        )

    asyncio.run(run())


def test_native_empty_lists_get_actionable_service_message(monkeypatch):
    messages(monkeypatch)
    validator = NativeValidatorWithFixtureLists()
    monkeypatch.setattr(validator, "codes", {})
    with pytest.raises(G2PRegistryException) as error:
        asyncio.run(
            validator.validate_records(
                [{"gender": "MALE"}], field_map={"gender": "GENDER"}
            )
        )
    assert error.value.message == MDS_UNAVAILABLE


def test_native_transport_failure_gets_actionable_service_message(monkeypatch):
    messages(monkeypatch)

    class Unreachable(NativeValidatorWithFixtureLists):
        async def _load(self):
            raise httpx.ConnectError("transport detail")

    with pytest.raises(G2PRegistryException) as error:
        asyncio.run(
            Unreachable().validate_records(
                [{"gender": "MALE"}], field_map={"gender": "GENDER"}
            )
        )
    assert error.value.message == MDS_UNAVAILABLE


def test_wrapper_does_not_override_native_enablement_or_loading():
    assert "enabled" not in am.AttributeValueValidator.__dict__
    assert "_load" not in am.AttributeValueValidator.__dict__


def test_wording_component_is_registered_ahead_of_core_and_is_idempotent():
    registry = am.component_registry
    saved = list(registry)
    try:
        registry[:] = [
            service
            for service in registry
            if not isinstance(service, am.G2PAttributeValueValidator)
        ]
        core = am.G2PAttributeValueValidator()
        wording = am.install_attribute_messages()
        assert am.G2PAttributeValueValidator.get_component() is wording
        assert registry.index(wording) < registry.index(core)
        assert am.install_attribute_messages() is wording
    finally:
        registry[:] = saved
