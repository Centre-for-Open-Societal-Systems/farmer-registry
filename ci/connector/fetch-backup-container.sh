#!/usr/bin/env bash
set -euo pipefail
set +x
: "${BACKUP_SSH_KEY:?Expected the development backup SSH credential}"
: "${CONNECTOR_BACKUP_DIRECTORY:?Expected a private backup destination}"
: "${IMAGE_TAG:?Expected the Farmer source image tag}"
docker build -t "coss-ci/services:$IMAGE_TAG" ci/services
mkdir -p "$(dirname "$CONNECTOR_BACKUP_DIRECTORY")"
docker run --rm --network host --user "$(id -u):$(id -g)" \
  -e HOME=/tmp/services-backup-home -e BACKUP_SSH_KEY -e CONNECTOR_BACKUP_DIRECTORY \
  -v "$PWD:$PWD" -w "$PWD" -v "$BACKUP_SSH_KEY:$BACKUP_SSH_KEY:ro" \
  -v "$(dirname "$CONNECTOR_BACKUP_DIRECTORY"):$(dirname "$CONNECTOR_BACKUP_DIRECTORY")" \
  "coss-ci/services:$IMAGE_TAG" python ci/connector/fetch_backup.py \
  --ssh-key "$BACKUP_SSH_KEY" --directory "$CONNECTOR_BACKUP_DIRECTORY"
