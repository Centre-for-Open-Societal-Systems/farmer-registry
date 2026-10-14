#!/usr/bin/env python3
"""Explicit IAM catalog registration using the chart's HTTP contract."""
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request


def request(url, data, headers):
    for attempt in range(12):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=15) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # Do not log token responses or credentials. Contract/auth errors
            # fail immediately; only service startup failures are retried.
            if error.code < 500:
                raise RuntimeError(f"HTTP {error.code}") from None
        except urllib.error.URLError:
            pass
        if attempt < 11:
            time.sleep(5)
    raise RuntimeError("service did not become ready")


def main():
    token = request(
        "http://keycloak.localtest.me:8080/realms/farmer/protocol/openid-connect/token",
        urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": "commons-services-staff-portal",
                               "client_secret": os.environ["COMMONS_CLIENT_SECRET"]}).encode(),
        {"Content-Type": "application/x-www-form-urlencoded"},
    )["access_token"]
    for filename, mnemonic, url, description in (
        ("farmer", "farmer-registry-staff-portal", "http://portal.farmer.localtest.me:3100", "Farmer Registry"),
        ("openg2p-master-data", "master-data", "http://masterdata.farmer.localtest.me:3110", "Master Data"),
        ("partner-management", "commons-services-staff-portal", "http://pm.farmer.localtest.me:3050", "Partner Management"),
        ("openg2p-awe", "awe-admin-portal", "http://awe.farmer.localtest.me:8131", "Approval Workflow Engine"),
    ):
        directory = Path(__file__).parent / "generated" if filename == "farmer" else Path(__file__).parent
        payload = json.loads((directory / (filename + "-catalog.json")).read_text())
        payload.update(application_mnemonic=mnemonic, application_url=url, application_description=description)
        request("http://iam-staff-api:8000/user-access/staff_portal_applications", json.dumps(payload).encode(),
                {"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        print(f"Registered {mnemonic}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Registration failed ({type(error).__name__}); check IAM/Keycloak service logs")
        raise SystemExit(1)
