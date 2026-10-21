#!/usr/bin/env bash
# Exercise upgrade/rehearsal control flow with fake tools; never access a cluster.
set -euo pipefail
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"' EXIT
mkdir "$STATE/bin"
cat > "$STATE/bin/docker" <<'MOCK'
#!/bin/sh
printf 'docker %s\n' "$*" >> "$CALLS"
case "$*" in
  *'oan_chart.py url'*) printf 'https://approved.example/chart.tgz\n' ;;
  *'cutover.py validate '*) exit "${VALIDATE_EXIT:-0}" ;;
  *'cutover.py backup '*) exit "${BACKUP_EXIT:-0}" ;;
  *'deployment.py unchanged '*) exit "${UNCHANGED_EXIT:-0}" ;;
  *'cutover.py attempt '*|*'cutover.py outcome '*|*'cutover.py rehearsal '*)
    for last; do :; done
    printf '{}\n' > "$last" ;;
esac
MOCK
cat > "$STATE/bin/helm" <<'MOCK'
#!/bin/sh
printf 'helm %s\n' "$*" >> "$CALLS"
MOCK
cat > "$STATE/bin/kubectl" <<'MOCK'
#!/bin/sh
printf 'kubectl %s\n' "$*" >> "$CALLS"
MOCK
cat > "$STATE/bin/curl" <<'MOCK'
#!/bin/sh
exit 0
MOCK
chmod +x "$STATE/bin/"*
export PATH="$STATE/bin:$PATH" CALLS="$STATE/calls"
export DELIVERY_ENVIRONMENT=dev HELM_NAMESPACE=farmer HELM_RELEASE=farmer-registry
export KUBECONFIG="$STATE/kubeconfig" IMAGE_TAG=abcdef012345
export REGISTRY_OUTCOME_FILE="$STATE/artifact.json" CUTOVER_BACKUP_DIRECTORY="$STATE/backup"
for mode in upgrade --rehearse; do
  : > "$CALLS"
  bash ci/deploy/cutover-dev.sh "$mode"
  grep -q '^helm template .*--no-hooks --post-renderer ci/deploy/cutover-renderer.sh' "$CALLS"
  if [[ "$mode" == upgrade ]]; then
    test "$(grep -c 'cutover.py backup ' "$CALLS")" = 2
    grep -q '^helm upgrade .*--no-hooks --post-renderer ci/deploy/cutover-renderer.sh --wait --timeout 20m' "$CALLS"
  else
    grep -q 'deployment.py unchanged ' "$CALLS"
    grep -q 'cutover.py rehearsal ' "$CALLS"
    if grep -Eq '^helm upgrade |cutover.py backup |cutover.py outcome ' "$CALLS"; then exit 1; fi
  fi
done
for gate in VALIDATE_EXIT BACKUP_EXIT UNCHANGED_EXIT; do
  export VALIDATE_EXIT=0 BACKUP_EXIT=0 UNCHANGED_EXIT=0
  export "$gate=1"
  mode=upgrade
  if [[ "$gate" == UNCHANGED_EXIT ]]; then mode=--rehearse; fi
  : > "$CALLS"
  if bash ci/deploy/cutover-dev.sh "$mode" > "$STATE/output" 2>&1; then exit 1; fi
  if grep -q '^helm upgrade ' "$CALLS"; then echo 'Failed gate allowed upgrade'; exit 1; fi
done
export VALIDATE_EXIT=0 BACKUP_EXIT=0 UNCHANGED_EXIT=0
unset CUTOVER_BACKUP_DIRECTORY
: > "$CALLS"
if bash ci/deploy/cutover-dev.sh > "$STATE/output" 2>&1; then exit 1; fi
test ! -s "$CALLS"
bash ci/deploy/cutover-dev.sh --rehearse > "$STATE/output"
export OAN_CHART_ARCHIVE="$STATE/chart.tgz" OAN_VALUES_FILE="$STATE/values.yaml"
bash ci/deploy/cutover-renderer.sh < /dev/null
grep -q 'OAN_CHART_ONLY.*:ro.*oan_compat.py' "$CALLS"
export HELM_NAMESPACE=far
: > "$CALLS"
if bash ci/deploy/cutover-dev.sh --rehearse > "$STATE/output" 2>&1; then exit 1; fi
test ! -s "$CALLS"
echo 'PASS: cutover/rehearsal, backup/preservation/revision gates and renderer wiring'
