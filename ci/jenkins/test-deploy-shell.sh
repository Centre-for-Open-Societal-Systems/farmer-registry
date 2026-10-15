#!/usr/bin/env bash
# Exercise the actual deployment script with fake tools; no cluster or Docker access.
set -euo pipefail
TEST_ROOT=$(mktemp -d)
trap 'rm -rf "$TEST_ROOT"' EXIT
mkdir "$TEST_ROOT/bin"
cat > "$TEST_ROOT/bin/docker" <<'MOCK'
#!/bin/sh
printf '%s\n' "$*" >> "$GUARD_CALLS"
case "$*" in
  *upgrade-mode*) printf '%s\n' "$TEST_MODE" ;;
esac
MOCK
cat > "$TEST_ROOT/bin/helm" <<'MOCK'
#!/bin/sh
printf '%s\n' "$*" >> "$HELM_CALLS"
if [ "$1" = upgrade ]; then exit "$TEST_UPGRADE_EXIT"; fi
MOCK
cat > "$TEST_ROOT/bin/kubectl" <<'MOCK'
#!/bin/sh
exit 0
MOCK
chmod +x "$TEST_ROOT/bin/"*
export PATH="$TEST_ROOT/bin:$PATH"
export KUBECONFIG="$TEST_ROOT/unused-kubeconfig"
export HELM_RELEASE=farmer-registry HELM_NAMESPACE=farmer
export ECR_REGISTRY=123456789012.dkr.ecr.ap-south-1.amazonaws.com IMAGE_TAG=abcdef012345
export HELM_CALLS="$TEST_ROOT/helm-calls"
export GUARD_CALLS="$TEST_ROOT/guard-calls"
for TEST_MODE in normal recovery; do
  for TEST_UPGRADE_EXIT in 0 1; do
    export TEST_MODE TEST_UPGRADE_EXIT
    : > "$HELM_CALLS"
    : > "$GUARD_CALLS"
    result=0
    bash ci/jenkins/deploy-dev.sh > "$TEST_ROOT/output" 2>&1 || result=$?
    if [ "$result" -ne "$TEST_UPGRADE_EXIT" ]; then
      cat "$TEST_ROOT/output"
      exit 1
    fi
    upgrade=$(grep '^upgrade ' "$HELM_CALLS")
    case "$upgrade" in
      *'--wait --wait-for-jobs --timeout 20m'*) ;;
      *) echo 'Missing readiness flags'; exit 1 ;;
    esac
    case "$TEST_MODE:$upgrade" in
      normal:*--atomic*) ;;
      recovery:*--atomic*) echo 'Recovery must not use atomic rollback'; exit 1 ;;
      normal:*) echo 'Normal upgrade must use atomic rollback'; exit 1 ;;
    esac
    if [ "$TEST_UPGRADE_EXIT" -eq 1 ]; then
      grep -q ' diagnose ' "$GUARD_CALLS"
      grep -q '^history ' "$HELM_CALLS"
      if grep -q '^get hooks ' "$HELM_CALLS"; then
        echo 'Failed upgrade must stop before post-upgrade validation'; exit 1
      fi
    else
      grep -q '^get hooks ' "$HELM_CALLS"
    fi
    echo "PASS: Bash $BASH_VERSION $TEST_MODE upgrade exit=$TEST_UPGRADE_EXIT"
  done
done
