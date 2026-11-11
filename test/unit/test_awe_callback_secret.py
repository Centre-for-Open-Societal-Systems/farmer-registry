"""AWE's callback_secret row follows the registry's HMAC Secret on every db-seed run.

The platform chart mints <release>-awe-callback-hmac again only when the Secret is gone, and the
platform template's upsert updated caller_service only, so a re-minted Secret left AWE signing with
the old value and every decision webhook was refused with 401. The db-seed entrypoint (registry
platform docker/db-seed/entrypoint.sh, run_callback_secret) substitutes exactly three variables
with envsubst and runs the result with psql ON_ERROR_STOP=0, so a broken statement would fail
silently: these checks read the template as text.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "farmer-extension/src/openg2p_registry_farmer_extension/awe_meta_data"
            / "40_callback_secret.sql.tpl").read_text(encoding="utf-8")
SQL = "\n".join(line for line in TEMPLATE.splitlines() if not line.lstrip().startswith("--"))
UPSERT = re.sub(r"\s+", " ", SQL.split("ON CONFLICT", 1)[1])


def test_only_the_entrypoints_three_variables_are_used():
    assert set(re.findall(r"\$\{?([A-Z_]+)", TEMPLATE)) == {
        "AWE_CALLBACK_SECRET_ID", "AWE_CALLBACK_CALLER_SERVICE", "AWE_CALLBACK_HMAC_SECRET"}


def test_a_re_minted_secret_replaces_the_stored_one():
    assert UPSERT.startswith(' ("id") DO UPDATE SET ')
    assert '"secret_hash" = EXCLUDED."secret_hash",' in UPSERT
    assert '"caller_service" = EXCLUDED."caller_service",' in UPSERT


def test_rotated_at_moves_only_when_the_value_changes():
    assert ('"rotated_at" = CASE WHEN EXCLUDED."secret_hash" IS DISTINCT FROM "callback_secret"."secret_hash" '
            'THEN NOW() ELSE "callback_secret"."rotated_at" END,') in UPSERT


def test_status_and_created_at_are_left_alone_on_conflict():
    # A revoked row stays revoked, and created_at keeps the first registration.
    assert '"status" =' not in UPSERT and '"created_at" =' not in UPSERT


def test_it_is_one_statement():
    assert SQL.count(";") == 1 and SQL.rstrip().endswith(";")
