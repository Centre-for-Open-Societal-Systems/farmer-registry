#!/usr/bin/env python3
"""
Sync submissions from ODK Central to OpenG2P Farmer Registry Partner API.
Usage:
    python3 odk/sync_from_central.py [password]
"""

import getpass
import json
import ssl
import sys
import urllib.request

ODK_CENTRAL_URL = "https://odk.13.207.43.8.nip.io"
PROJECT_ID = 13
FORM_ID = "farmer_profile"
EMAIL = "meghakinassery@gmail.com"
PARTNER_API_URL = "http://localhost:8006/partner/ingest_data"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def login_odk_central(email, password):
    print(f"[*] Logging in to ODK Central as {email}...")
    url = f"{ODK_CENTRAL_URL}/v1/sessions"
    data = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, context=ctx) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        token = res.get("token")
        print("[+] Logged in successfully. Token acquired.")
        return token


def expand_navigation_links(obj, token):
    if isinstance(obj, dict):
        for key in list(obj.keys()):
            val = obj[key]
            if key.endswith("@odata.navigationLink") and isinstance(val, str):
                clean_key = key.split("@")[0]
                url = f"{ODK_CENTRAL_URL}/v1/projects/{PROJECT_ID}/forms/{FORM_ID}.svc/{val}"
                try:
                    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
                    with urllib.request.urlopen(req, context=ctx) as resp:
                        sub_data = json.loads(resp.read().decode("utf-8"))
                        obj[clean_key] = sub_data.get("value", [])
                        print(f"    [+] Expanded repeat '{clean_key}': {len(obj[clean_key])} record(s)")
                except Exception as e:
                    print(f"    [!] Warning: Failed to expand {clean_key}: {e}")
            else:
                expand_navigation_links(val, token)
    elif isinstance(obj, list):
        for item in obj:
            expand_navigation_links(item, token)


def fetch_submissions(token):
    print(f"[*] Fetching submissions for form '{FORM_ID}' (Project {PROJECT_ID})...")
    url = f"{ODK_CENTRAL_URL}/v1/projects/{PROJECT_ID}/forms/{FORM_ID}.svc/Submissions?$expand=*"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, context=ctx) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        submissions = data.get("value", [])
        print(f"[+] Found {len(submissions)} submission(s) in ODK Central.")
        for sub in submissions:
            expand_navigation_links(sub, token)
        return submissions


def send_to_partner_api(submission):
    instance_id = submission.get("__id", "submission-01")
    clean_id = instance_id.replace("uuid:", "")
    print(f"[*] Forwarding submission '{instance_id}' to Partner API...")
    payload = {
        "header": {
            "message_id": clean_id,
            "sender_id": "farmer-partner"
        },
        "message": submission
    }
    req = urllib.request.Request(
        f"{PARTNER_API_URL}?data_model=FARMER_ODK_MODEL&intake_form_id=a1a4d25a-1cd4-4356-abac-8782382649",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "partner-id": "farmer-partner",
        },
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("[+] Successfully ingested into OpenG2P:")
        print(json.dumps(res, indent=2))
        return res


def main():
    password = sys.argv[1] if len(sys.argv) > 1 else None
    if not password:
        password = getpass.getpass(f"Enter ODK Central password for {EMAIL}: ")

    try:
        token = login_odk_central(EMAIL, password)
        submissions = fetch_submissions(token)
        if not submissions:
            print("[-] No submissions found to sync.")
            return

        for sub in submissions:
            send_to_partner_api(sub)

        print("\n[✔] Sync complete! Open Staff Portal to view intake submissions:")
        print("    👉 http://localhost:3001/en/intake-form/farmer")
    except Exception as e:
        print(f"[!] Error: {e}")


if __name__ == "__main__":
    main()
