#!/usr/bin/env bash
# Same tools on both Jenkins nodes; no host Python/venv installation needed.
set -euo pipefail
set +x
action=${1:?Expected build or deploy}
case "$action" in build|deploy) ;; *) exit 1 ;; esac
tag=${IMAGE_TAG:-$(git rev-parse --short=12 HEAD)}
docker build -t "coss-ci/services:$tag" ci/services
args=(--rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp/services-home
      -e ECR_REGISTRY -e AWS_REGION -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY
      -e AWS_SESSION_TOKEN -e CONNECTOR_BACKUP_DIRECTORY
      -e KUBECONFIG_CREDENTIAL
      -v "$PWD:$PWD" -w "$PWD")
if [[ "$action" == build ]]; then
  args+=(-v /var/run/docker.sock:/var/run/docker.sock
         --group-add "$(stat -c %g /var/run/docker.sock)")
fi
for variable in KUBECONFIG DEV_MANIFEST DEV_ACCEPTANCE; do
  value=${!variable:-}
  if [[ -n "$value" ]]; then
    test -f "$value"
    args+=(-e "$variable" -v "$value:$value:ro")
  fi
done
if [[ -n "${CONNECTOR_BACKUP_DIRECTORY:-}" ]]; then
  if [[ -d "$CONNECTOR_BACKUP_DIRECTORY" ]]; then
    args+=(-v "$CONNECTOR_BACKUP_DIRECTORY:$CONNECTOR_BACKUP_DIRECTORY:ro")
  else
    # The coordinator fails the connector independently; dashboards can proceed.
    unset CONNECTOR_BACKUP_DIRECTORY
  fi
fi
docker run "${args[@]}" "coss-ci/services:$tag" bash ci/services/run.sh "$@"
