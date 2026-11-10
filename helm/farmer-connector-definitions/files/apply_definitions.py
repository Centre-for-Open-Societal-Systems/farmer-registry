"""Apply the connector definitions declared in Helm values to the connector API.

Runs as a Helm post-install/post-upgrade hook Job, with the connector image (stdlib
only). For every declared definition it creates the connector if it is missing,
otherwise PATCHes it to the declared state, and for WebSub receivers it then asks the
connector to register and subscribe its callback with the hub
(POST /connectors/{id}/websub/sync-subscriptions). Re-running changes nothing that
is already right.

Rows are matched by name (unique), then by `previous_names`, then by webhook slug.
Secrets arrive only as environment variables filled from Kubernetes Secrets:

  CD_<index>_WEBHOOK_SECRET      the row's webhook_secret
  CD_<index>_AUTH_<FIELD>        one field of auth_secret_json (EMAIL, PASSWORD, ...)

A secret that is declared but empty never overwrites the stored value: an existing
row keeps what it has (a warning is logged), a new row that needs it is an error.
No secret value is ever printed.
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CONFIG_PATH = os.environ.get("CD_CONFIG", "/config/definitions.json")
SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"

# Fields the connector API accepts on PATCH (ConnectorUpdate) and on POST (ConnectorCreate).
JSON_TEXT_FIELDS = ("source_config", "poll_config", "validation_schema")
PLAIN_FIELDS = (
    "enabled", "paused", "data_model_mnemonic", "mapper_expression", "mapper_version",
    "g2p_sender_id", "g2p_register_mnemonic", "auth_type", "webhook_path_slug",
    "webhook_verifier", "max_in_flight",
)
CREATE_REQUIRED = ("name", "platform", "transport_type", "g2p_sender_id", "g2p_register_mnemonic")
IMMUTABLE = ("platform", "transport_type")
SECRET_FIELDS = ("webhook_secret", "auth_secret_json")


class ApplyError(Exception):
    pass


def log(message: str) -> None:
    print(message, flush=True)


# ---------------------------------------------------------------------------
# Pure functions (unit tested)
# ---------------------------------------------------------------------------

def env_name(index: int, kind: str, field: str = "") -> str:
    base = f"CD_{index}_{kind}"
    return f"{base}_{field.upper()}" if field else base


def desired_body(definition: dict, index: int, environ: dict) -> tuple[dict, dict]:
    """Return (body, notes). body is the API payload; secrets are included only if set."""
    body: dict = {"name": definition["name"]}
    for field in PLAIN_FIELDS + IMMUTABLE:
        if definition.get(field) is not None:
            body[field] = definition[field]
    for field in JSON_TEXT_FIELDS:
        if definition.get(field) is not None:
            body[f"{field}_json"] = json.dumps(definition[field])
    notes: dict = {"missing_secrets": []}
    if definition.get("webhook_secret_from"):
        value = environ.get(env_name(index, "WEBHOOK_SECRET"), "")
        if value:
            body["webhook_secret"] = value
        else:
            notes["missing_secrets"].append("webhook_secret")
    auth_from = definition.get("auth_secret_from") or {}
    if auth_from:
        fields = {f: environ.get(env_name(index, "AUTH", f), "") for f in auth_from}
        if all(fields.values()):
            body["auth_secret_json"] = json.dumps(fields)
        else:
            notes["missing_secrets"].append("auth_secret_json")
    return body, notes


def _same(field: str, want, have) -> bool:
    if field.endswith("_json") and want is not None:
        try:
            return json.loads(want) == (json.loads(have) if have else None)
        except (TypeError, ValueError):
            return False
    return want == have


def changed_fields(body: dict, existing: dict) -> list[str]:
    """Names of non-secret fields in body that differ from the connector as the API returns it."""
    return [f for f, want in body.items() if f not in SECRET_FIELDS and not _same(f, want, existing.get(f))]


def find_existing(definition: dict, rows: list[dict]) -> dict | None:
    by_name = {r["name"]: r for r in rows}
    for name in [definition["name"], *definition.get("previous_names", [])]:
        if name in by_name:
            return by_name[name]
    slug = definition.get("webhook_path_slug")
    if slug:
        for row in rows:
            if row.get("webhook_path_slug") == slug:
                return row
    return None


def plan_definition(definition: dict, index: int, rows: list[dict], environ: dict) -> dict:
    """Decide what to do for one definition. Returns {action, body, existing, notes}."""
    body, notes = desired_body(definition, index, environ)
    existing = find_existing(definition, rows)
    if existing is None:
        missing = [f for f in CREATE_REQUIRED if not body.get(f)]
        if missing:
            raise ApplyError(f"{definition['name']}: cannot create, missing {', '.join(missing)}")
        if notes["missing_secrets"]:
            raise ApplyError(
                f"{definition['name']}: cannot create, the Kubernetes Secret for "
                f"{', '.join(notes['missing_secrets'])} is not available")
        return {"action": "create", "body": body, "existing": None, "notes": notes}
    for field in IMMUTABLE:
        if field in body and body[field] != existing.get(field):
            raise ApplyError(
                f"{definition['name']}: {field} is {existing.get(field)!r} and cannot be changed "
                f"to {body[field]!r}; retire the row and declare a new one")
    patch = {k: v for k, v in body.items() if k not in IMMUTABLE}
    diff = changed_fields(patch, existing)
    has_secret = any(f in patch for f in SECRET_FIELDS)
    action = "patch" if diff or has_secret else "unchanged"
    return {"action": action, "body": patch, "existing": existing, "notes": notes, "changed": diff}


def wants_subscription(definition: dict) -> bool:
    return (definition.get("transport_type") == "websub"
            and definition.get("subscribe", True) and definition.get("enabled", True)
            and not definition.get("paused", False))


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def http(method: str, url: str, token: str | None = None, body=None, form: dict | None = None,
         timeout: int = 60, context=None) -> tuple[int, object]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read()
        status = error.code
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, raw.decode("utf-8", "replace")[:300]


def read_client_secret(admin: dict) -> str:
    """Read the Keycloak client secret from its Secret through the Kubernetes API."""
    ref = admin["clientSecret"]
    with open(f"{SA_DIR}/token") as handle:
        sa_token = handle.read().strip()
    context = ssl.create_default_context(cafile=f"{SA_DIR}/ca.crt")
    url = f"https://kubernetes.default.svc/api/v1/namespaces/{ref['namespace']}/secrets/{ref['name']}"
    status, payload = http("GET", url, token=sa_token, context=context, timeout=20)
    if status != 200:
        raise ApplyError(
            f"cannot read Secret {ref['namespace']}/{ref['name']} (HTTP {status}); the Job's "
            f"ServiceAccount needs the read grant in ci/k8s")
    value = (payload.get("data") or {}).get(ref["key"], "")
    if not value:
        raise ApplyError(f"Secret {ref['namespace']}/{ref['name']} has no key {ref['key']}")
    return base64.b64decode(value).decode()


def mint_token(admin: dict) -> str:
    secret = read_client_secret(admin)
    status, payload = http("POST", admin["tokenUrl"], form={
        "grant_type": "client_credentials", "client_id": admin["clientId"], "client_secret": secret})
    if status != 200 or not isinstance(payload, dict) or "access_token" not in payload:
        raise ApplyError(f"Keycloak refused the {admin['clientId']} client-credentials grant (HTTP {status})")
    return payload["access_token"]


def wait_for_api(base: str, attempts: int = 60, delay: int = 5) -> None:
    for attempt in range(1, attempts + 1):
        try:
            status, _ = http("GET", f"{base}/health", timeout=10)
            if status == 200:
                return
        except OSError:
            pass
        log(f"connector API not ready (attempt {attempt}/{attempts})")
        time.sleep(delay)
    raise ApplyError(f"connector API {base} did not become ready")


def checked(status: int, payload, what: str, ok=(200, 201, 202, 204)):
    if status not in ok:
        detail = payload if isinstance(payload, str) else json.dumps(payload)[:300]
        raise ApplyError(f"{what}: HTTP {status} {detail}")
    return payload


def subscribe(base: str, token: str | None, connector_id: str, name: str, tries: int = 4, delay: int = 15) -> None:
    for attempt in range(1, tries + 1):
        status, payload = http("POST", f"{base}/connectors/{connector_id}/websub/sync-subscriptions", token=token)
        if status == 200 and isinstance(payload, dict) and payload.get("all_subscribe_ok"):
            log(f"{name}: subscribed {payload.get('topics_attempted')} at {payload.get('hub_url')}")
            return
        results = payload.get("results", []) if isinstance(payload, dict) else []
        summary = [{k: r.get(k) for k in ("topic", "register_http_status", "subscribe_http_status", "subscribe_error")}
                   for r in results]
        log(f"{name}: subscription attempt {attempt}/{tries} not accepted (HTTP {status}) {summary}")
        if attempt < tries:
            time.sleep(delay)
    raise ApplyError(f"{name}: the hub did not accept the subscription")


def main() -> int:
    with open(CONFIG_PATH) as handle:
        config = json.load(handle)
    base = config["apiBase"].rstrip("/")
    wait_for_api(base)
    token = mint_token(config["adminAuth"]) if config.get("adminAuth", {}).get("enabled") else None
    status, rows = http("GET", f"{base}/connectors", token=token)
    rows = checked(status, rows, "list connectors")
    failures: list[str] = []
    for index, definition in enumerate(config.get("definitions", [])):
        name = definition["name"]
        try:
            plan = plan_definition(definition, index, rows, os.environ)
            for field in plan["notes"]["missing_secrets"]:
                log(f"{name}: WARNING the Secret for {field} is empty; the stored value is kept")
            if plan["action"] == "create":
                status, created = http("POST", f"{base}/connectors", token=token, body=plan["body"])
                connector_id = checked(status, created, f"{name}: create")["connector_id"]
                log(f"{name}: created {connector_id}")
            else:
                connector_id = plan["existing"]["connector_id"]
                if plan["action"] == "patch":
                    status, patched = http("PATCH", f"{base}/connectors/{connector_id}", token=token, body=plan["body"])
                    checked(status, patched, f"{name}: patch")
                    log(f"{name}: updated {connector_id} (changed: {plan['changed'] or 'secrets only'})")
                else:
                    log(f"{name}: unchanged {connector_id}")
            if wants_subscription(definition):
                subscribe(base, token, connector_id, name)
        except ApplyError as error:
            failures.append(str(error))
            log(f"FAILED {error}")
    for name in config.get("retired", []):
        row = next((r for r in rows if r["name"] == name), None)
        if row is None:
            log(f"{name}: already retired")
            continue
        try:
            status, deleted = http("DELETE", f"{base}/connectors/{row['connector_id']}", token=token)
            checked(status, deleted, f"{name}: delete")
            log(f"{name}: retired {row['connector_id']}")
        except ApplyError as error:
            failures.append(str(error))
            log(f"FAILED {error}")
    if failures:
        log(f"{len(failures)} definition(s) failed")
        return 1
    log("All declared connector definitions are applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
