"""Every refusal the staff UI may show is one message without '; '.

A refusal that lists several problems joins them with '; ' (household_intake.py,
required_fields.py), and the staff UI's notice counts the parts
("N fields need attention", ui/staff-ui/overrides/src/oan/intake/serverNotice.ts).
A single message holding '; ' was shown as two problems: G2R-574 showed
"2 fields need attention: Already submitted on 19 Nov 2026; it is waiting for approval".
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("openg2p_registry_core")

from openg2p_registry_oan_farmer_extension.awe_error_message import awe_error_message
from openg2p_registry_oan_farmer_extension.register_domain.services import (
    household_intake as hi,
)
from openg2p_registry_oan_farmer_extension.register_domain.services.direct_approval import (
    DIRECT_APPROVAL_MESSAGE,
)
from openg2p_registry_oan_farmer_extension.register_domain.services.form_integrity import (
    MESSAGES,
)


def _form(approval_status):
    return SimpleNamespace(draft_status="FINAL", approval_status=approval_status,
                           finalized_at=datetime(2026, 11, 19, 9, 30))


def test_single_refusals_hold_no_part_separator():
    said = [hi.already_submitted(_form(status)) for status in ("PENDING", "APPROVED", "REJECTED")]
    said += [DIRECT_APPROVAL_MESSAGE, awe_error_message(404, "{}"), awe_error_message(409, "[]")]
    said += list(MESSAGES.values())
    for message in said:
        assert "; " not in message, message
