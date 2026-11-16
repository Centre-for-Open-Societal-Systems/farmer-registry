#!/usr/bin/env bash
# Bring the staging Farmer connector (releases farmer-connector-credentials and farmer-registry-connector, namespace
# farmer) to oan-helm main's staging values and to the connector images of the build just promoted, the way crop and
# livestock upgrade their connector after the registry. Run by ci/pipelines/staging.groovy right after
# promote-staging.sh; it takes no parameters.
#
# Which image: the promoted chart (built-chart/*.tgz, left by oan-helm's deliver_staging.sh) records the develop commit
# it was packaged from (annotation oan.org/source-commit). Its first 12 characters are the build tag that develop build
# pushed the registry-connector and registry-connector-ui images with; their digests are resolved from ECR. ECR keeps a
# tag on one image only, so a later develop build of the same commit can move the tag off the promoted staff-api digest;
# a build tag still on that digest is tried after the chart's commit. Nothing is built or tagged here, and no tag is
# guessed: if the build has no connector image the run fails before the cluster is touched. Same rules as livestock's
# ci/connector/upgrade-livestock-connector-staging.sh.
#
# What runs is oan-helm's own scripts/ci/deliver_staging_farmer_connector.sh with its chart (addons/farmer-connector,
# addons/farmer-connector-credentials) and its values (environments/staging/values/farmer-connector*.yaml), plus the
# image override written below: helm upgrade --install --reset-values --atomic --wait, so git and the promoted build are
# the only sources and a failed upgrade restores the previous revision (chart and values only). The image pinned in
# farmer-connector.yaml is the fallback the override replaces. Without this step the release kept the values of its
# last operator deploy: after the qa move the connector still validated the old issuer (staging #45,
# connector-definitions: "Invalid issuer").
#
# Env: KUBECONFIG and AWS credentials (set by the pipeline); PROMOTED_CHART (default: the one archive in built-chart/);
# PLAN_ONLY=1 stops after printing the images, before oan-helm is fetched or the cluster is touched.
set -euo pipefail
set +x
umask 077
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
: "${KUBECONFIG:?The pipeline must bind the staging kubeconfig}"
: "${AWS_REGION:=ap-south-1}"
: "${PLAN_ONLY:=0}"
# A build tag: the commit12 tag develop pushes, or <version>-<branch>.<build>.
BUILD_TAG_PATTERN='^([0-9a-f]{12}|[0-9]+\.[0-9]+\.[0-9]+-[a-z0-9-]+\.[1-9][0-9]*)$'
# The rc tag the promotion adds to the chart's images is not a build: the connector images never carry it.
PROMOTION_TAG_PATTERN='^[0-9]+\.[0-9]+\.[0-9]+-rc\.[0-9]+$'
PROMOTED_CHART="${PROMOTED_CHART:-$(ls built-chart/*.tgz 2> /dev/null | head -n 1)}"
test -f "${PROMOTED_CHART:-}" || { echo "No promoted chart archive (built-chart/*.tgz): the registry promotion must run first." >&2; exit 1; }
STATE=$(mktemp -d)
checkout=.oan-helm-connector
trap 'rm -rf "$STATE" "$checkout"' EXIT

# 1. The connector images of the build that was promoted.
# Functions, not here-documents inside <( ): bash 4.2 (the build agents) cannot parse them in a process substitution.
promoted_service_image() {
  python3 - "$1" <<'PY'
import re, sys, tarfile
with tarfile.open(sys.argv[1]) as bundle:
    member = next(m for m in bundle.getmembers() if m.name.count("/") == 1 and m.name.endswith("/values.yaml"))
    values = bundle.extractfile(member).read().decode("utf-8")
repository = None
for line in values.splitlines():
    found = re.match(r"""^\s*repository:\s*["']?(\S+?/staff-api(?:-[0-9][0-9A-Za-z.-]*)?)["']?\s*$""", line)
    if found:
        repository = found.group(1)
        continue
    found = re.match(r"""^\s*(?:tag|digest):\s*["']?(?:[^"'@\s]+@)?(sha256:[0-9a-f]{64})["']?\s*$""", line)
    if found and repository:
        print(repository, found.group(1))
        break
else:
    sys.exit("the promoted chart pins no staff-api image by digest")
PY
}
promoted_source_commit() {
  python3 - "$1" <<'PY'
import re, sys, tarfile
with tarfile.open(sys.argv[1]) as bundle:
    member = next(m for m in bundle.getmembers() if m.name.count("/") == 1 and m.name.endswith("/Chart.yaml"))
    chart = bundle.extractfile(member).read().decode("utf-8")
found = re.search(r"""^\s+oan\.org/source-commit:\s*["']?([0-9a-f]{40})["']?\s*$""", chart, re.M)
print(found.group(1)[:12] if found else "")
PY
}
read -r SERVICE_REPOSITORY SERVICE_DIGEST < <(promoted_service_image "$PROMOTED_CHART")
test -n "${SERVICE_DIGEST:-}" || { echo "no staff-api digest in $PROMOTED_CHART" >&2; exit 1; }
SOURCE_BUILD_TAG=$(promoted_source_commit "$PROMOTED_CHART")
# staff-api, or staff-api-<RP version> under versioned names: the connector images carry the same suffix.
SERVICE_NAME=${SERVICE_REPOSITORY##*/}
PLATFORM_SUFFIX=${SERVICE_NAME#staff-api}
IMAGE_PREFIX=${SERVICE_REPOSITORY%/*}
ECR_BASE=${IMAGE_PREFIX#*/}
CONNECTOR_IMAGE_REPOSITORY="$IMAGE_PREFIX/registry-connector$PLATFORM_SUFFIX"
CONNECTOR_UI_IMAGE_REPOSITORY="$IMAGE_PREFIX/registry-connector-ui$PLATFORM_SUFFIX"
ecr_digest() {
  aws ecr describe-images --region "$AWS_REGION" --repository-name "$1" --image-ids "imageTag=$2" \
    --query 'imageDetails[0].imageDigest' --output text 2> /dev/null || true
}
digest_tags=$(aws ecr describe-images --region "$AWS_REGION" --repository-name "$ECR_BASE/$SERVICE_NAME" \
  --image-ids "imageDigest=$SERVICE_DIGEST" --query 'imageDetails[0].imageTags[]' --output text | tr '\t' '\n' \
  | grep -E "$BUILD_TAG_PATTERN" | grep -v -E "$PROMOTION_TAG_PATTERN" | sort || true)
build_tags=$(printf '%s\n' "$SOURCE_BUILD_TAG" $digest_tags | grep -E "$BUILD_TAG_PATTERN" | awk '!seen[$0]++' || true)
test -n "$build_tags" || { echo "Neither the promoted chart (oan.org/source-commit) nor staff-api $SERVICE_DIGEST names a build tag matching $BUILD_TAG_PATTERN." >&2; exit 1; }
CONNECTOR_IMAGE_DIGEST=""
for tag in $build_tags; do
  CONNECTOR_IMAGE_DIGEST=$(ecr_digest "$ECR_BASE/registry-connector$PLATFORM_SUFFIX" "$tag")
  CONNECTOR_UI_IMAGE_DIGEST=$(ecr_digest "$ECR_BASE/registry-connector-ui$PLATFORM_SUFFIX" "$tag")
  if [[ "$CONNECTOR_IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ && "$CONNECTOR_UI_IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    BUILD_TAG=$tag
    break
  fi
  CONNECTOR_IMAGE_DIGEST=""
done
test -n "$CONNECTOR_IMAGE_DIGEST" || { echo "No registry-connector and registry-connector-ui image carries a build tag of the promoted staff-api ($build_tags)." >&2; exit 1; }
echo "Promoted chart is build $BUILD_TAG (chart commit ${SOURCE_BUILD_TAG:-none recorded}; staff-api $SERVICE_DIGEST)"
echo "api, worker, beat, consumer: $CONNECTOR_IMAGE_REPOSITORY@$CONNECTOR_IMAGE_DIGEST"
echo "ui: $CONNECTOR_UI_IMAGE_REPOSITORY@$CONNECTOR_UI_IMAGE_DIGEST"

# oan-helm's addons/farmer-connector takes repository plus tag "<tag>@<digest>" (environments/staging/values/farmer-connector.yaml).
OVERRIDE="$STATE/connector-images.values.json"
python3 - "$OVERRIDE" "$CONNECTOR_IMAGE_REPOSITORY" "$CONNECTOR_IMAGE_DIGEST" "$CONNECTOR_UI_IMAGE_REPOSITORY" "$CONNECTOR_UI_IMAGE_DIGEST" "$BUILD_TAG" <<'PY'
import json, sys
path, repository, digest, ui_repository, ui_digest, tag = sys.argv[1:7]
override = {name: {"image": {"repository": repository, "tag": f"{tag}@{digest}"}} for name in ("api", "worker", "beat", "consumer")}
override["ui"] = {"image": {"repository": ui_repository, "tag": f"{tag}@{ui_digest}"}}
json.dump(override, open(path, "w"), indent=2)
PY
if [[ "$PLAN_ONLY" == 1 ]]; then
  echo "PLAN_ONLY: nothing was changed."
  exit 0
fi

# 2. oan-helm's delivery, with the override after its staging values.
rm -rf "$checkout"
git clone --quiet --depth 1 --filter=blob:none --sparse \
  https://github.com/Centre-for-Open-Societal-Systems/oan-helm.git "$checkout"
git -C "$checkout" sparse-checkout set scripts/ci environments/staging/values addons/farmer-connector \
  addons/farmer-connector-credentials
echo "oan-helm main $(git -C "$checkout" rev-parse --short=12 HEAD)"
helm history farmer-registry-connector -n farmer --max 2 || true
bash "$checkout/scripts/ci/deliver_staging_farmer_connector.sh" --values "$OVERRIDE"
helm history farmer-registry-connector -n farmer --max 2

# 3. The running workloads are the promoted build's connector.
for d in api worker beat ui; do
  want_repository=$CONNECTOR_IMAGE_REPOSITORY want_digest=$CONNECTOR_IMAGE_DIGEST
  if [[ "$d" == ui ]]; then want_repository=$CONNECTOR_UI_IMAGE_REPOSITORY want_digest=$CONNECTOR_UI_IMAGE_DIGEST; fi
  got=$(kubectl get deployment -n farmer "farmer-registry-connector-$d" -o jsonpath='{.spec.template.spec.containers[0].image}')
  case "$got" in
    "$want_repository:$BUILD_TAG@$want_digest"|"$want_repository@$want_digest") ;;
    *) echo "farmer-registry-connector-$d runs $got, not build $BUILD_TAG" >&2; exit 1 ;;
  esac
done
echo "Farmer connector upgraded to build $BUILD_TAG"
