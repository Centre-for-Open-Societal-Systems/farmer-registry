#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
mkdir -p "$HOME"
if [[ "${1:-}" == build ]]; then
  : "${ECR_REGISTRY:?Missing ECR registry}"
  export DOCKER_CONFIG
  DOCKER_CONFIG=$(mktemp -d)
  trap 'rm -rf "$DOCKER_CONFIG"' EXIT
  aws ecr get-login-password --region "${AWS_REGION:-ap-south-1}" |
    docker login --username AWS --password-stdin "$ECR_REGISTRY"
fi
python ci/services/coordinator.py "$@"
