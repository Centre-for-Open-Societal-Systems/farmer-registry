#!/usr/bin/env bash
# Build the Farmer Registry images and test the extension inside them.
#
# The registry images are upstream's published Farmer images with the OAN
# extension installed (docker/<component>/Dockerfile), the same images the local stack runs. The
# sanity suite is upstream's (docker/sanity-tests). Images are tagged
# coss-ci/<component>:<tag>; the publish stage pushes them under these names.
set -euo pipefail
tag="${1:?usage: ci/build/images.sh <image tag>}"

for component in staff-api partner-api celery db-seed staff-ui; do
  docker build -f "docker/$component/Dockerfile" -t "coss-ci/$component:$tag" .
done

# Load each Python image's platform entry point offline, as the image starts it.
for role in staff-api partner-api celery-worker celery-beat; do
  image="coss-ci/${role/#celery-*/celery}:$tag"
  docker run --rm --network none -v "$PWD:/repo:ro" --entrypoint python "$image" /repo/ci/validation/check_image_boot.py "$role"
done

# Exercise real native SAVE (including parent/finance rejection and complete
# rollback) in the exact Celery image that Jenkins will publish.
OAN_WORKER_SAVE_TEST_IMAGE="coss-ci/celery:$tag" python3 ci/validation/check_native_worker_save.py
docker build -f docker/sanity-tests/Dockerfile -t "coss-ci/sanity-tests:$tag" .

# The connector image (docker/registry-connector): OpenG2P's published connector plus
# openg2p_registry_connector_extension, with the extension's tests run inside it.
docker build -f docker/registry-connector/Dockerfile -t "coss-ci/registry-connector:$tag" .
docker run --rm -u 0 -v "$PWD/docker/registry-connector:/ext:ro" -w /ext -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint sh "coss-ci/registry-connector:$tag" -c \
  'pip install --quiet --no-cache-dir --root-user-action=ignore pytest==8.4.2 && python -m pytest -q -p no:cacheprovider tests'

# The extension's tests, against the platform it is installed on. They read
# upstream UI files from the repository, so the whole tree is mounted.
for component in staff-api; do
  docker run --rm -v "$PWD:/repo:ro" -w /repo/farmer-extension -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo/farmer-extension/src:/repo/farmer-extension/tests \
    --entrypoint sh "coss-ci/$component:$tag" -c \
    'pip install --quiet --no-cache-dir pytest==8.4.2 && python -m pytest -q -p no:cacheprovider tests'
done

# Native DDL and reporting are rehearsed in an owned disposable PostgreSQL.
OAN_METADATA_TEST_IMAGE="coss-ci/staff-api:$tag" python3 ci/validation/check_native_metadata.py

# Load extensions exactly as the unmodified native launcher does.
for mode in worker beat; do
  docker run --rm --network none -v "$PWD:/repo:ro" --entrypoint python "coss-ci/celery:$tag" /repo/ci/validation/check_worker_extensions.py "$mode"
done
