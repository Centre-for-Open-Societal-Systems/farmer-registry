#!/usr/bin/env python3
"""Run inside the staff image with its startup entrypoint bypassed (read only)."""
import asyncio
import json
import urllib.request

import check_geo_schema


def main():
    failed = False
    for name, url in {
        "IAM": "http://iam-staff-api:8000/ping",
        "AWE": "http://awe:8000/v1/awe/health",
        "Master Data": "http://farmer-master-data-api:8000/ping",
        "PM partner": "http://pm-partner-api:8000/ping",
        "CM partner": "http://cm-partner-api:8000/ping",
        "MinIO": "http://minio.farmer.localtest.me:9100/minio/health/live",
    }.items():
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                if response.status != 200:
                    raise RuntimeError("unhealthy")
            print(f"OK: {name}")
        except Exception as error:
            print(f"FAIL: {name} ({type(error).__name__})")
            failed = True
    try:
        issuer = "http://keycloak.localtest.me:8080/realms/farmer"
        with urllib.request.urlopen(issuer + "/.well-known/openid-configuration", timeout=10) as response:
            assert json.load(response)["issuer"] == issuer
        print("OK: browser/backend issuer agree")
    except Exception as error:
        print(f"FAIL: Keycloak discovery ({type(error).__name__})")
        failed = True
    try:
        failed = bool(asyncio.run(check_geo_schema.check())) or failed
    except Exception as error:
        print(f"FAIL: coordinate schema ({type(error).__name__})")
        failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
