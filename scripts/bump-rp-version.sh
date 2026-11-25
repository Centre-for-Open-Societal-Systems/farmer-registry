#!/usr/bin/env bash
# Move this repository to another OpenG2P registry-platform version (rpVersion) in one change.
#
# As in OpenG2P, the platform version is the ARG BASE_IMAGE_VERSION default of the Dockerfiles: a Dockerfile cannot
# read it from another file before FROM, and a plain `docker build -f docker/<role>/Dockerfile .` must work without
# arguments. Every copy must agree (test/unit/test_base_image_pin_lockstep.py), so this script writes them together:
#
#   docker/{staff-api,partner-api,celery,db-seed,sanity-tests}/Dockerfile   ARG BASE_IMAGE_VERSION=<rpVersion>
#   docker/staff-ui/Dockerfile                  ARG BASE_IMAGE_VERSION=<rpCommit>, the org.opencontainers.image.revision
#                                                label of openg2p/openg2p-registry-staff-ui:<rpVersion>
#   helm/openg2p-farmer-registry/Chart.yaml     appVersion and the openg2p-registry dependency version
#   helm/openg2p-farmer-registry/Chart.lock     helm dependency update
#   ci/validation/native-release-contract.json  platformVersion (the reviewed native release contract)
#
# ci/deploy/oan-chart.json (the central chart archive, pinned by SHA-256) is not written: it moves in its own reviewed
# pin change once a central chart for the new platform is published. Until then
# test/unit/test_base_image_pin_lockstep.py names it as the one copy that differs.
#
# The version is always explicit: there is no automatic "latest". It must exist as an openg2p-registry chart in the
# OpenG2P Helm index and as openg2p/openg2p-registry-staff-ui on Docker Hub. A new rpVersion means new ECR repositories
# for the six platform images; the develop pipeline creates them (ci/build/ecr_repository.py).
#
#   scripts/bump-rp-version.sh <version>       write the new version
#   scripts/bump-rp-version.sh -n <version>    check it and show what would change; write nothing
#
# Requires: bash, curl, python3, helm. Run from the repository root.
set -euo pipefail

CHART_DIR="helm/openg2p-farmer-registry"
HELM_INDEX="https://openg2p.github.io/openg2p-helm/index.yaml"
CONTRACT="ci/validation/native-release-contract.json"

die() { echo "ERROR: $*" >&2; exit 1; }

CHECK_ONLY=false
VERSION=""
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)
      # The header above, without tools: help works on an agent that has none of them.
      n=0
      while IFS= read -r line; do
        n=$((n + 1)); [ "$n" -ge 2 ] || continue; [ "${line:0:1}" = "#" ] || break
        line=${line#\#}; printf '%s\n' "${line# }"
      done < "$0"
      exit 0 ;;
    -n|--check|--dry-run) CHECK_ONLY=true; shift ;;
    -*) die "unknown option '$1' (see --help)" ;;
    *) [ -z "$VERSION" ] || die "unexpected extra argument '$1'"; VERSION="$1"; shift ;;
  esac
done
[ -n "$VERSION" ] || die "give the platform version, for example: scripts/bump-rp-version.sh 1.2.2-rc.681"
[ -f docker/staff-ui/Dockerfile ] && [ -d "$CHART_DIR" ] || die "run from the repository root"
command -v curl >/dev/null && command -v python3 >/dev/null && command -v helm >/dev/null \
  || die "curl, python3 and helm are required"

INDEX=$(mktemp); trap 'rm -f "$INDEX"' EXIT
curl -fsSL "$HELM_INDEX" -o "$INDEX" || die "could not read $HELM_INDEX"
grep -qF "openg2p-registry-$VERSION.tgz" "$INDEX" || die "no openg2p-registry $VERSION chart in $HELM_INDEX"
COMMIT=$(python3 - "$VERSION" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("check_rp_commit", "ci/build/check_rp_commit.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
try:
    commit = module.revision(sys.argv[1])
except Exception as error:
    sys.exit("openg2p/openg2p-registry-staff-ui:%s cannot be read: %s" % (sys.argv[1], error))
if not commit:
    sys.exit("openg2p/openg2p-registry-staff-ui:%s has no revision label" % sys.argv[1])
print(commit)
PY
) || die "$COMMIT"

CURRENT=$(python3 ci/deploy/image_names.py platform) || die "the Dockerfiles do not agree on one platform version"
echo "rpVersion: $CURRENT -> $VERSION"
echo "rpCommit:  $(python3 ci/deploy/image_names.py platform-commit) -> $COMMIT"
if [ "$CHECK_ONLY" = true ]; then
  echo "(check only: nothing written)"
  exit 0
fi

python3 - "$VERSION" "$COMMIT" "$CHART_DIR/Chart.yaml" "$CONTRACT" <<'PY'
import json, re, sys
version, commit, chart, contract = sys.argv[1:]

def rewrite(path, pattern, replacement, flags=0):
    text = open(path, encoding="utf-8").read()
    new, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        sys.exit("%s: %s not found" % (path, pattern))
    open(path, "w", encoding="utf-8").write(new)

for role in ("staff-api", "partner-api", "celery", "db-seed", "sanity-tests"):
    rewrite("docker/%s/Dockerfile" % role, r"(?m)^(ARG BASE_IMAGE_VERSION=)\S+", r"\g<1>" + version)
rewrite("docker/staff-ui/Dockerfile", r"(?m)^(ARG BASE_IMAGE_VERSION=)\S+", r"\g<1>" + commit)
rewrite("docker/staff-ui/Dockerfile", r"(openg2p/openg2p-registry-staff-ui:)\S+?(\.?)$", r"\g<1>" + version + r"\g<2>",
        re.M)
rewrite(chart,r"(?m)^(appVersion:\s*)\S+", r"\g<1>" + version)
# Only the version inside the openg2p-registry dependency block.
rewrite(chart, r"(-\s*name:\s*openg2p-registry\b(?:(?!\n\s*-\s).)*?version:\s*)\S+", r"\g<1>" + version, re.S)
data = json.load(open(contract, encoding="utf-8"))
data["platformVersion"] = version
open(contract, "w", encoding="utf-8").write(json.dumps(data, indent=2) + "\n")
PY

helm repo add openg2p https://openg2p.github.io/openg2p-helm >/dev/null 2>&1 || true
helm repo update openg2p >/dev/null
helm dependency update "$CHART_DIR" >/dev/null || die "helm dependency update failed for $VERSION"
[ "$(python3 ci/deploy/image_names.py platform)" = "$VERSION" ] || die "post-write check failed: the Dockerfiles differ"
python3 ci/build/check_rp_commit.py "$VERSION" "$(python3 ci/deploy/image_names.py platform-commit)"

echo ""
echo "Written: the six Dockerfiles, $CHART_DIR/Chart.yaml, $CHART_DIR/Chart.lock, $CONTRACT."
echo "Not written: ci/deploy/oan-chart.json (the central chart pin moves in its own reviewed change)."
echo "Run: python -m pytest test/unit/test_base_image_pin_lockstep.py"
