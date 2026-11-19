"""Create a missing ECR repository for a Farmer image the way the existing ones are made. Run by the develop pipeline.

    python3 ci/build/ecr_repository.py ensure <repository> <template repository>

A repository that exists is left alone. A missing one (a new image, or every platform image after an rpVersion bump:
oan-helm docs/release/naming-standard.md, section 6) is created with the tag mutability and encryption of the template
(the image's repository before the eoan names), scan on push always on, the tags owner=farmer-registry and
naming=eoan-standard, and the template's lifecycle policy when it has one. Nothing is ever created by hand.

Needs the aws CLI with the pipeline's ECR credential. Standard library only. Exit codes: 0 exists or created, 1 failure.
"""
import json
import subprocess
import sys

REGION = "ap-south-1"
TAGS = ["Key=owner,Value=farmer-registry", "Key=naming,Value=eoan-standard"]


class Missing(Exception):
    pass


def aws(args):
    """stdout of `aws ecr <args>`; Missing for a repository or lifecycle policy that does not exist."""
    result = subprocess.run(["aws", "ecr", "--region", REGION] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True)
    if result.returncode:
        if "RepositoryNotFoundException" in result.stderr or "LifecyclePolicyNotFoundException" in result.stderr:
            raise Missing()
        raise RuntimeError("aws ecr %s failed: %s" % (args[0], result.stderr.strip().splitlines()[-1:] or ""))
    return result.stdout


def ensure(name, template, call=aws):
    """'exists' or 'created'. The template must exist: its settings are the reviewed ones."""
    try:
        call(["describe-repositories", "--repository-names", name, "--output", "json"])
        return "exists"
    except Missing:
        pass
    try:
        settings = json.loads(call(["describe-repositories", "--repository-names", template,
                                    "--output", "json"]))["repositories"][0]
    except Missing:
        raise RuntimeError("template repository %s does not exist; create %s through a reviewed change" % (template, name))
    encryption = settings.get("encryptionConfiguration") or {"encryptionType": "AES256"}
    call(["create-repository", "--repository-name", name,
          "--image-tag-mutability", settings.get("imageTagMutability", "IMMUTABLE"),
          "--image-scanning-configuration", "scanOnPush=true",
          "--encryption-configuration", "encryptionType=" + encryption["encryptionType"]
          + (",kmsKey=" + encryption["kmsKey"] if encryption.get("kmsKey") else ""),
          "--tags"] + TAGS)
    try:
        policy = json.loads(call(["get-lifecycle-policy", "--repository-name", template, "--output", "json"]))
    except Missing:
        policy = None
    if policy and policy.get("lifecyclePolicyText"):
        call(["put-lifecycle-policy", "--repository-name", name, "--lifecycle-policy-text", policy["lifecyclePolicyText"]])
    return "created"


def main(argv):
    if len(argv) != 4 or argv[1] != "ensure":
        print("usage: ecr_repository.py ensure <repository> <template repository>", file=sys.stderr)
        return 1
    try:
        print("%s: %s" % (argv[2], ensure(argv[2], argv[3])))
        return 0
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print("FAIL: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
