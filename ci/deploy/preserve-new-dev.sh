#!/usr/bin/env bash
# Existing Jenkins/VPN route and existing backup SSH credential only.
set -euo pipefail
set +x
: "${BACKUP_SSH_KEY:?Bind farmer-new-dev-backup-ssh}"
: "${SOURCE_COMMIT:?Actual delivery checkout required}"
: "${IMAGE_TAG:?Service image tag required}"
test "${NEW_DEV_RESET_ACTION:-check}" = check
case "${OAN_DELIVERY_ACTION:-}" in preserve-preflight) mode=preflight ;; preserve-upgrade) mode=execute ;; *) exit 1 ;; esac
docker build -t "coss-ci/services:$IMAGE_TAG" ci/services
args=(--mode "$mode" --ssh-key "$BACKUP_SSH_KEY")
if [[ -n "${FARMER_ADOPTION_RECOVERY_DIRECTORY:-}" ]]; then args+=(--recovery-directory "$FARMER_ADOPTION_RECOVERY_DIRECTORY"); fi
exec docker run --rm --network host --user "$(id -u):$(id -g)" \
  -e SOURCE_COMMIT -e HOME=/tmp/services-preserve-home \
  -v "$PWD:$PWD" -w "$PWD" -v "$BACKUP_SSH_KEY:$BACKUP_SSH_KEY:ro" \
  "coss-ci/services:$IMAGE_TAG" python ci/deploy/preserve_entry.py "${args[@]}"
