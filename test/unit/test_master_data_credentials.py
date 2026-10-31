from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("environment", ["dev", "staging"])
def test_registry_master_data_uses_its_existing_required_secret(environment):
    values = yaml.safe_load((ROOT / f"helm/environments/{environment}/farmer-identity.yaml").read_text())
    for component, prefix in [("staffApi", "REGISTRY_STAFF_PORTAL_API_"), ("partnerApi", "REGISTRY_PARTNER_API_"), ("celeryWorker", "REGISTRY_CELERY_WORKERS_")]:
        env = values["registry"][component]["envVars"]
        assert env[prefix + "MASTER_DATA_CLIENT_ID"] == "farmer-registry-staff-portal"
        assert values["registry"][component]["envVarsFrom"][prefix + "MASTER_DATA_CLIENT_SECRET"] == {"secretKeyRef": {
            "name": "farmer-registry-staff-portal", "key": "client_secret", "optional": False}}
        assert env[prefix + "MASTER_DATA_TOKEN_URL"].startswith(values["global"]["keycloakBaseUrl"] + "/realms/staff/")
