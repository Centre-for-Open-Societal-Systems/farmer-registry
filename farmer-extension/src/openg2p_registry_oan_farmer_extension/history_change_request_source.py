"""Load register history change_request_source as the platform's enum.

The platform maps the column as String, but get_record_history reads
``change_request_source.value``, so every history call failed with
"'str' object has no attribute 'value'". Converting the loaded value to
ChangeRequestSourceEnum (a StrEnum, so it still equals and serialises as the
stored text) makes the platform method work unchanged.
"""
import logging

from openg2p_registry_core.models import G2PRegisterHistory
from openg2p_registry_core.models.enum import ChangeRequestSourceEnum
from sqlalchemy import event
from sqlalchemy.orm.attributes import set_committed_value

_logger = logging.getLogger("oan-history-change-request-source")


def as_change_request_source(target):
    value = getattr(target, "change_request_source", None)
    if not isinstance(value, str) or isinstance(value, ChangeRequestSourceEnum):
        return
    try:
        set_committed_value(target, "change_request_source", ChangeRequestSourceEnum(value))
    except ValueError:
        _logger.warning("Unknown change request source %r on %s", value, type(target).__name__)


def _on_load(target, _context):
    as_change_request_source(target)


def install():
    """Idempotent: one load listener for every register history class."""
    if not event.contains(G2PRegisterHistory, "load", _on_load):
        event.listen(G2PRegisterHistory, "load", _on_load, propagate=True)
