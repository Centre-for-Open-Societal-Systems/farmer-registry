"""Exercise PM 1.0.2 on the isolated local stack using its native HTTP APIs.

Run: uv run --no-project python tests/e2e/local/test_pm_approval.py
The host launcher targets ONLY farmer-upstream-partner-api. It creates synthetic
PM partners, retaining their audit history; it never accesses the dev server.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


def local_test():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    admin = "http://pm-staff-api:8000"
    public = "http://pm-partner-api:8000"

    def call(method, url, data=None, token=None, expected=200):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(url, method=method, headers=headers,
                                         data=json.dumps(data).encode() if data is not None else None)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status, body = response.status, json.load(response)
        except urllib.error.HTTPError as error:
            status, body = error.code, json.load(error)
        assert status == expected, f"{method} {url}: HTTP {status}, expected {expected}"
        return body

    prefix = "REGISTRY_PARTNER_API_PARTNER_MGMT_ADMIN_"
    request = urllib.request.Request(os.environ[prefix + "TOKEN_URL"], data=urllib.parse.urlencode({
        "grant_type": "client_credentials", "client_id": os.environ[prefix + "CLIENT_ID"],
        "client_secret": os.environ[prefix + "CLIENT_SECRET"],
    }).encode())
    with urllib.request.urlopen(request, timeout=20) as response:
        token = json.load(response)["access_token"]
    call("GET", admin + "/partners", expected=401)
    call("GET", admin + "/partners", token="invalid-token", expected=401)
    call("GET", admin + "/partners", token=token)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    pem = key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    run_id = uuid.uuid4().hex[:12]
    evidence = {"run_id": run_id, "partners": []}
    for decision in ("approve", "reject"):
        partner = f"pm-local-{run_id}-{decision}"
        request = call("POST", admin + "/partners/requests/onboarding", {
            "partner_id": partner, "name": "Local PM acceptance " + decision,
            "org_name": "Synthetic local test", "description": "Local PM lifecycle acceptance",
            "keys": [{"public_key": pem, "kid": "local-test-key"}],
        }, token)
        assert request["status"] == "created"
        request_id = request["id"]
        partner_url = admin + "/partners/" + partner
        key_url = public + "/keys/" + partner
        assert call("GET", partner_url, token=token)["status"] == "created"
        call("GET", key_url, expected=404)
        pending = call("GET", admin + "/partners/requests?" + urllib.parse.urlencode({
            "partner_id": partner, "status": "created"}), token=token)
        assert [r["id"] for r in pending["requests"]] == [request_id]
        result = call("POST", admin + f"/partners/requests/{request_id}/{decision}",
                      {"notes": "Synthetic local acceptance"}, token)
        assert result["status"] == ("approved" if decision == "approve" else "rejected")
        assert result["reviewed_by"] and result["submitted_by"]
        # PM 1.0.2 wraps PM-REQ-409 in the platform HTTP 400 envelope.
        repeated = call("POST", admin + f"/partners/requests/{request_id}/{decision}", {}, token, expected=400)
        assert "PM-REQ-409" in json.dumps(repeated)
        if decision == "approve":
            assert call("GET", partner_url, token=token)["status"] == "active"
            keys = call("GET", key_url)["keys"]
            assert len(keys) == 1 and keys[0]["kid"] == "local-test-key"
            fetched = serialization.load_pem_public_key(keys[0]["public_key"].encode())
            assert fetched.public_numbers() == key.public_numbers()
            call("POST", partner_url + "/disable", {}, token)
            call("GET", key_url, expected=404)
            call("POST", partner_url + "/enable", {}, token)
            assert len(call("GET", key_url)["keys"]) == 1
            # Leave synthetic partners disabled; retain the audit evidence.
            call("POST", partner_url + "/disable", {}, token)
        else:
            assert call("GET", partner_url, token=token)["status"] == "created"
            call("GET", key_url, expected=404)
        audit = call("GET", partner_url + "/audit", token=token)
        events = [e for e in audit["events"] if e.get("request_id") == request_id]
        actions = {e["action"] for e in events}
        assert "request.submitted" in actions
        assert "request." + result["status"] in actions
        assert all(e.get("actor_name") or e.get("actor_id") for e in events)
        evidence["partners"].append({"partner_id": partner, "request_id": request_id,
                                     "decision": result["status"]})
    print(json.dumps(evidence))


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside-local-container"]:
        local_test()
    elif not sys.argv[1:]:
        result = subprocess.run(["docker", "exec", "-i", "farmer-upstream-partner-api",
                                 "python", "-", "--inside-local-container"],
                                input=Path(__file__).read_text(encoding="utf-8"), text=True,
                                capture_output=True)
        if result.returncode:
            # Avoid raw HTTP/auth exception output, which can contain credentials.
            print("FAIL: local PM lifecycle test. Check local PM logs; no server was contacted.")
            # Assertion messages contain only method, URL and status, never tokens.
            for line in result.stderr.splitlines():
                if line.startswith("AssertionError:"):
                    print(line)
            raise SystemExit(1)
        evidence = json.loads(result.stdout)
        output = Path(__file__).parent / "generated" / "pm-approval-acceptance.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print("PASS: local PM auth, onboarding, approve/reject, repeat decision, keys, disable/enable and audit")
    else:
        raise SystemExit("This acceptance runner only targets the isolated local stack")
