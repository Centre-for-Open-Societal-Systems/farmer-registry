#!/usr/bin/env bash
# Exercise staging's real shell sequencing (OAN chart in namespace farmer) with fake tools, no cluster access.
set -euo pipefail
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"' EXIT
mkdir "$STATE/bin"
cat > "$STATE/bin/docker" <<'MOCK'
#!/bin/sh
printf 'guard %s\n' "$*" >> "$CALLS"
case "$*" in
  *'staging.py cutover '*) exit "$CUTOVER_EXIT" ;;
  *'oan_chart.py require-deployable '*) exit "${GATE_EXIT:-0}" ;;
  *upgrade-mode*) printf 'normal\n' ;;
  *'oan_chart.py url'*) printf 'https://approved.example/chart.tgz\n' ;;
esac
MOCK
cat > "$STATE/bin/curl" <<'MOCK'
#!/bin/sh
exit 0
MOCK
cat > "$STATE/bin/python3" <<'MOCK'
#!/bin/sh
printf 'python3 %s\n' "$*" >> "$CALLS"
exit 0
MOCK
cat > "$STATE/bin/helm" <<'MOCK'
#!/bin/sh
printf 'helm %s\n' "$*" >> "$CALLS"
MOCK
cat > "$STATE/bin/kubectl" <<'MOCK'
#!/bin/sh
printf 'kubectl %s\n' "$*" >> "$CALLS"
MOCK
chmod +x "$STATE/bin/"*
export PATH="$STATE/bin:$PATH"
export CALLS="$STATE/calls" DELIVERY_ENVIRONMENT=staging HELM_NAMESPACE=farmer
export HELM_RELEASE=farmer-registry KUBECONFIG="$STATE/kubeconfig"
export KUBECONFIG_CREDENTIAL=staging-farmer-kubeconfig
export ECR_REGISTRY=recorded-in-protected-evidence IMAGE_TAG=abcdef012345
export SOURCE_COMMIT=abcdef012345abcdef012345abcdef012345abcd
export STAGING_EVIDENCE_FILE="$STATE/private-evidence.json"
for CUTOVER_EXIT in 0 1; do
  export CUTOVER_EXIT
  : > "$CALLS"
  result=0
  bash ci/deploy/deploy-rc.sh > "$STATE/output" 2>&1 || result=$?
  test "$result" = "$CUTOVER_EXIT" || { cat "$STATE/output"; exit 1; }
  grep -q 'staging.py cluster ' "$CALLS"
  grep -q 'oan_chart.py require-deployable staging' "$CALLS"
  grep -q 'staging.py cutover ' "$CALLS"
  if [[ "$CUTOVER_EXIT" == 1 ]]; then
    if grep -q '^helm upgrade ' "$CALLS"; then echo 'Unrehearsed staging deployment ran'; exit 1; fi
  else
    grep -q '^helm upgrade .* -n farmer ' "$CALLS"
    grep -q '^helm upgrade .*--post-renderer ci/deploy/oan-renderer.sh' "$CALLS"
    grep -q '^helm template .*--post-renderer ci/deploy/oan-renderer.sh' "$CALLS"
    if grep '^helm upgrade ' "$CALLS" | grep -Eq -- '--atomic|--install'; then
      echo 'Staging must not install or automatically revert schema-dependent images'; exit 1
    fi
    if grep -Eq '^helm (repo|dependency) ' "$CALLS"; then echo 'Staging must use only the pinned OAN archive'; exit 1; fi
    grep -q '^helm get hooks ' "$CALLS"
    grep -q 'deploy/farmer-registry-staff-portal-api -c staff-portal-api' "$CALLS"
    # The seed metadata checks run on staging exactly as on dev.
    grep -q 'python3 scripts/operations/commons/check_seed_metadata.py .*90_checks.sql' "$CALLS"
    if grep -q '^kubectl create ' "$CALLS"; then echo 'The legacy stopped-workload probe must not run'; exit 1; fi
  fi
done
# Only the OAN pin made for staging may be deployed to staging.
export CUTOVER_EXIT=0 GATE_EXIT=1
: > "$CALLS"
if bash ci/deploy/deploy-rc.sh > "$STATE/output" 2>&1; then
  echo 'A pin for another environment was accepted'; exit 1
fi
if grep -Eq '^helm (upgrade|template|lint) ' "$CALLS"; then echo 'Chart used before the pin gate'; exit 1; fi
unset GATE_EXIT
# The legacy namespace and other pairs are rejected before any tool runs.
for pair in "staging far" "staging commons" "dev far"; do
  set -- $pair
  : > "$CALLS"
  if DELIVERY_ENVIRONMENT=$1 HELM_NAMESPACE=$2 bash ci/deploy/deploy-rc.sh > "$STATE/output" 2>&1; then
    echo "Cross-environment namespace accepted: $pair"; exit 1
  fi
  test ! -s "$CALLS"
done
echo "PASS: Bash $BASH_VERSION staging evidence, OAN pin, namespace and recovery sequencing"
