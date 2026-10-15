#!/usr/bin/env bash
# Check host/container boundaries without Docker, kubeconfig or cloud access.
set -euo pipefail
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"' EXIT
mkdir "$STATE/bin"
cat > "$STATE/bin/docker" <<'MOCK'
#!/bin/sh
printf '<%s>\n' "$@" >> "$CONTAINER_TEST_CALLS"
MOCK
cat > "$STATE/bin/stat" <<'MOCK'
#!/bin/sh
printf '1000\n'
MOCK
chmod +x "$STATE/bin/"*
export PATH="$STATE/bin:$PATH"
export CONTAINER_TEST_CALLS="$STATE/calls"
export IMAGE_TAG=abcdef012345
export AWS_SECRET_ACCESS_KEY=synthetic-test-value-must-not-appear
export KUBECONFIG="$STATE/private kubeconfig"
export DEV_MANIFEST="$STATE/private manifest.json"
export DEV_ACCEPTANCE="$STATE/private acceptance.json"
touch "$KUBECONFIG" "$DEV_MANIFEST" "$DEV_ACCEPTANCE"
for action in build deploy; do
  : > "$CONTAINER_TEST_CALLS"
  bash ci/services/run-container.sh "$action" --environment dev --registry example.invalid --output /tmp/test-only.json
  grep -Fxq '<AWS_SECRET_ACCESS_KEY>' "$CONTAINER_TEST_CALLS"
  if grep -Fq 'synthetic-test-value-must-not-appear' "$CONTAINER_TEST_CALLS"; then
    echo 'Credential value exposed in process arguments'; exit 1
  fi
  grep -Fxq "<$KUBECONFIG:$KUBECONFIG:ro>" "$CONTAINER_TEST_CALLS"
  grep -Fxq "<$DEV_MANIFEST:$DEV_MANIFEST:ro>" "$CONTAINER_TEST_CALLS"
  grep -Fxq "<$DEV_ACCEPTANCE:$DEV_ACCEPTANCE:ro>" "$CONTAINER_TEST_CALLS"
  if [[ "$action" == build ]]; then
    grep -Fq '</var/run/docker.sock:/var/run/docker.sock>' "$CONTAINER_TEST_CALLS"
  elif grep -Fq '/var/run/docker.sock' "$CONTAINER_TEST_CALLS"; then
    echo 'Deployment must not mount a Docker socket'; exit 1
  fi
  echo "PASS: Bash $BASH_VERSION optional $action secret-file mounts and credential boundaries"
done
