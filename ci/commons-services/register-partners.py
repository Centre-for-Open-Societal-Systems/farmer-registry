"""Make sure every partner in the JSON on stdin is active in Partner Management.

Run by upgrade.sh inside the partner-management staff-portal-api pod, which
ships httpx and reaches Keycloak and the API in-cluster. Registry platform 1.2
resolves each ingest's sender against Partner Management, so a sender missing
here makes every submission from it fail.

Authenticates as the commons-services-staff-portal client (client credentials),
whose service account holds the partner_manager role the chart's kc-sa-role hook
assigns. Idempotent:

    absent              -> onboarding request, then approve it
    created (pending)   -> approve its open onboarding request
    disabled            -> enable
    active              -> nothing

Environment: PM_API_URL, PM_TOKEN_URL, PM_CLIENT_ID. Stdin: the client secret
on the first line, then the partner list as JSON.
"""
import json
import os
import sys

import httpx

api = os.environ["PM_API_URL"].rstrip("/")
client_secret = sys.stdin.readline().strip()
partners = json.load(sys.stdin)
token = httpx.post(
    os.environ["PM_TOKEN_URL"],
    data={
        "grant_type": "client_credentials",
        "client_id": os.environ["PM_CLIENT_ID"],
        "client_secret": client_secret,
    },
    timeout=30,
)
token.raise_for_status()
client = httpx.Client(
    base_url=api,
    headers={"Authorization": f"Bearer {token.json()['access_token']}"},
    timeout=30,
)


def call(method, path, **kwargs):
    r = client.request(method, path, **kwargs)
    if r.status_code >= 400 and not (method == "GET" and r.status_code == 404):
        sys.exit(f"[partners] {method} {path} -> {r.status_code} {r.text}")
    return r


def approve_open_onboarding(partner_id):
    reqs = call("GET", "/partners/requests", params={"partner_id": partner_id, "status": "created"}).json()
    open_reqs = [q for q in reqs.get("requests", []) if q.get("request_type") == "onboarding"]
    if not open_reqs:
        sys.exit(f"[partners] {partner_id} is pending but has no open onboarding request")
    call("POST", f"/partners/requests/{open_reqs[0]['id']}/approve", json={"notes": "commons-services upgrade"})


for p in partners:
    pid = p["partner_id"]
    r = call("GET", f"/partners/{pid}")
    if r.status_code == 404:
        created = call(
            "POST",
            "/partners/requests/onboarding",
            json={
                "partner_id": pid,
                "name": p["name"],
                "org_name": p.get("org_name"),
                "description": p.get("description"),
                "keys": [{"public_key": p["public_key"]}],
            },
        ).json()
        call("POST", f"/partners/requests/{created['id']}/approve", json={"notes": "commons-services upgrade"})
        action = "onboarded and approved"
    else:
        status = r.json().get("status")
        if status == "active":
            action = "already active"
        elif status == "disabled":
            call("POST", f"/partners/{pid}/enable")
            action = "re-enabled"
        else:
            approve_open_onboarding(pid)
            action = "pending onboarding approved"
    final = call("GET", f"/partners/{pid}").json().get("status")
    if final != "active":
        sys.exit(f"[partners] {pid} is '{final}' after: {action}")
    print(f"[partners] {pid}: {action}")
