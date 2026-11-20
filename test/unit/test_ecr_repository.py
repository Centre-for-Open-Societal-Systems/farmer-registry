"""ci/build/ecr_repository.py with a stand-in aws: the standard settings, nothing done to an existing repository."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ecr_repository", ROOT / "ci/build/ecr_repository.py")
ecr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ecr)
NEW = "eoan/farmer-registry/staff-api-1.2.2-rc.681"
OLD = "openg2p/farmer-registry/staff-api"
POLICY = '{"rules":[{"rulePriority":1}]}'


class Aws:
    def __init__(self, existing, policies):
        self.existing, self.policies, self.calls = set(existing), dict(policies), []

    def __call__(self, args):
        self.calls.append(args)
        if args[0] == "describe-repositories":
            if args[2] not in self.existing:
                raise ecr.Missing()
            return json.dumps({"repositories": [{"repositoryName": args[2]}]})
        if args[0] == "get-lifecycle-policy":
            if args[2] not in self.policies:
                raise ecr.Missing()
            return json.dumps({"lifecyclePolicyText": self.policies[args[2]]})
        return ""


def option(call, name):
    return call[call.index(name) + 1]


def test_an_existing_repository_is_left_alone():
    aws = Aws({NEW, OLD}, {OLD: POLICY})
    assert ecr.ensure(NEW, OLD, aws) == "exists"
    assert [c[0] for c in aws.calls] == ["describe-repositories"]


def test_a_missing_repository_gets_the_standard_settings_and_the_old_lifecycle_policy():
    aws = Aws({OLD}, {OLD: POLICY})
    assert ecr.ensure(NEW, OLD, aws) == "created"
    create = next(c for c in aws.calls if c[0] == "create-repository")
    assert option(create, "--repository-name") == NEW
    assert option(create, "--image-tag-mutability") == "IMMUTABLE"
    assert option(create, "--image-scanning-configuration") == "scanOnPush=true"
    assert option(create, "--encryption-configuration") == "encryptionType=AES256"
    assert create[create.index("--tags") + 1:] == ["Key=owner,Value=farmer-registry", "Key=naming,Value=eoan-standard"]
    put = aws.calls[-1]
    assert put[0] == "put-lifecycle-policy" and option(put, "--repository-name") == NEW
    assert option(put, "--lifecycle-policy-text") == POLICY


@pytest.mark.parametrize("existing", [{OLD}, set()])
def test_without_a_template_policy_none_is_set(existing):
    aws = Aws(existing, {})
    assert ecr.ensure(NEW, OLD, aws) == "created"
    assert aws.calls[-1][0] == "get-lifecycle-policy"
