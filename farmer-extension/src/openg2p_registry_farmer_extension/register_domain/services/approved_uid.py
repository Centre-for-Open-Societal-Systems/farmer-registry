"""Keep the lookup identity aligned with approved Farmer UID records."""
import logging
import re
from datetime import date
from sqlalchemy import select, text

_logger = logging.getLogger("g2p-register-domain-service")


def fan_value(value):
    value = "".join(str(value or "").split()).upper().removeprefix("FAN-")
    return value if re.fullmatch(r"[0-9]{16}", value) else None


def choose_projection(current, rows, approved_history=(), today=None):
    """Project a unique current FAN; retain independently supplied identities.

    Historical approved UID values identify an existing UID-derived projection,
    allowing approved replacements/revocations without overwriting other IDs.
    """
    today = today or date.today()
    owned_values = {fan_value(v) for v in approved_history}
    candidates = set()
    for row in rows:
        if str(row.get("id_type") or "").upper() != "UID":
            continue
        value = fan_value(row.get("value"))
        if not value or not row.get("last_approved_at") or not row.get("last_approved_by"):
            continue
        owned_values.add(value)
        expiry = row.get("expiry_date")
        expiry = date.fromisoformat(str(expiry)[:10]) if expiry else None
        if row.get("record_status") == "ACTIVE" and row.get("status") == "VALID" and (not expiry or expiry >= today):
            candidates.add(value)
    canonical = fan_value(current)
    managed = canonical is not None and canonical in owned_values
    candidate = next(iter(candidates)) if len(candidates) == 1 else None
    if current and not managed and canonical != candidate:
        return current, "independent-identity-preserved"
    if len(candidates) > 1:
        return (None if managed else current), "ambiguous-approved-uids"
    if candidate:
        return candidate, "approved-uid"
    return (None if managed else current), "no-current-approved-fan"


async def sync_approved_uid(session, internal_record_id):
    if not internal_record_id:
        return "no-parent"
    from openg2p_registry_extensions.register_domain.models import G2PRegisterFarmer
    farmer = (await session.execute(select(G2PRegisterFarmer).where(
        G2PRegisterFarmer.internal_record_id == internal_record_id).with_for_update())).scalar_one_or_none()
    if farmer is None:
        return "not-a-farmer"
    rows = (await session.execute(text("""
        SELECT id_type,value,status,record_status,expiry_date,last_approved_at,last_approved_by
        FROM g2p_register_reg_ids WHERE link_internal_record_id=:parent
    """), {"parent":internal_record_id})).mappings().all()
    history = (await session.execute(text("""
        SELECT value FROM g2p_register_history_reg_ids
        WHERE link_internal_record_id=:parent AND id_type='UID'
          AND approved_at IS NOT NULL AND approved_by IS NOT NULL
    """), {"parent":internal_record_id})).scalars().all()
    projected, reason = choose_projection(farmer.foundational_id, rows, history)
    if projected == farmer.foundational_id:
        return reason
    if projected:
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                                  {"key":"farmer-approved-fan:"+projected})
        conflict = (await session.execute(text("""
            SELECT 1 FROM g2p_register_farmers
            WHERE internal_record_id<>:parent AND foundational_id=:fan
            UNION ALL
            SELECT 1 FROM g2p_register_reg_ids
            WHERE link_internal_record_id<>:parent AND id_type='UID'
              AND status='VALID' AND record_status='ACTIVE'
              AND last_approved_at IS NOT NULL AND last_approved_by IS NOT NULL
              AND (expiry_date IS NULL OR expiry_date>=CURRENT_DATE)
              AND regexp_replace(regexp_replace(upper(trim(value)),'^FAN-',''),'[[:space:]]','','g')=:fan
            LIMIT 1
        """), {"parent":internal_record_id,"fan":projected})).first()
        if conflict:
            _logger.warning("Approved UID projection skipped: identity belongs to another Farmer")
            return "identity-conflict"
    farmer.foundational_id = projected
    await session.flush()
    _logger.info("Approved UID projection synchronized (%s)", reason)
    return reason
