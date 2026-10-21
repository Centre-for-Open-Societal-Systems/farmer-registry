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
  *'oan_chart.py url'*) printf 'https://approved.example/chart.tgz\n' ;;
  *'oan_chart.py verify '*) exit "${TEST_VERIFY_EXIT:-0}" ;;
esac
MOCK
cat > "$TEST_ROOT/bin/curl" <<'MOCK'
#!/bin/sh
exit "${TEST_DOWNLOAD_EXIT:-0}"
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
export IDENTITY_EVIDENCE_FILE="$TEST_ROOT/identity-evidence.json"
for APPLY_COMMONS_IDENTITY in false true; do
  export APPLY_COMMONS_IDENTITY
for TEST_MODE in normal recovery; do
  for TEST_UPGRADE_EXIT in 0 1; do
    export TEST_MODE TEST_UPGRADE_EXIT
    : > "$HELM_CALLS"
    : > "$GUARD_CALLS"
    result=0
    bash ci/deploy/deploy-dev.sh > "$TEST_ROOT/output" 2>&1 || result=$?
    if [ "$result" -ne "$TEST_UPGRADE_EXIT" ]; then
      cat "$TEST_ROOT/output"
      exit 1
    fi
    upgrade=$(grep '^upgrade ' "$HELM_CALLS")
    lint=$(grep '^lint ' "$HELM_CALLS" | cut -d ' ' -f2)
    render=$(grep '^template ' "$HELM_CALLS" | cut -d ' ' -f3)
    package=$(printf '%s' "$upgrade" | cut -d ' ' -f3)
    test "$lint" = "$package" && test "$render" = "$package"
    case "$package" in */oan-farmer.tgz) ;; *) exit 1 ;; esac
    if grep -Eq '^dependency |^repo ' "$HELM_CALLS"; then exit 1; fi
    grep -q '^template .*--post-renderer ci/deploy/oan-renderer.sh' "$HELM_CALLS"
    printf '%s' "$upgrade" | grep -q -- '--post-renderer ci/deploy/oan-renderer.sh'
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
    if [ "$APPLY_COMMONS_IDENTITY" = true ]; then
      grep -q ':/identity-evidence.json:ro' "$GUARD_CALLS"
    elif grep -q ':/identity-evidence.json:ro' "$GUARD_CALLS"; then
      echo 'Default deployment must not mount identity evidence'; exit 1
    fi
    echo "PASS: Bash $BASH_VERSION $TEST_MODE identity=$APPLY_COMMONS_IDENTITY upgrade exit=$TEST_UPGRADE_EXIT"
  done
done
done
export TEST_UPGRADE_EXIT=0 TEST_MODE=normal APPLY_COMMONS_IDENTITY=false
for gate in download verify; do
  export TEST_DOWNLOAD_EXIT=0 TEST_VERIFY_EXIT=0
  if [[ "$gate" = download ]]; then export TEST_DOWNLOAD_EXIT=1; else export TEST_VERIFY_EXIT=1; fi
  : > "$HELM_CALLS"
  if bash ci/deploy/deploy-dev.sh > "$TEST_ROOT/output" 2>&1; then
    echo 'Failed OAN package gate was accepted'; exit 1
  fi
  if grep -Eq '^upgrade |^lint |^template ' "$HELM_CALLS"; then exit 1; fi
done
echo 'PASS: download/checksum failures stop before any chart use'
