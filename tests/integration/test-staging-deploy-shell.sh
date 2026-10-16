#!/usr/bin/env bash
# Exercise staging's real shell sequencing with fake tools, no cluster access.
set -euo pipefail
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"' EXIT
mkdir "$STATE/bin"
cat > "$STATE/bin/docker" <<'MOCK'
#!/bin/sh
printf 'guard %s\n' "$*" >> "$CALLS"
case "$*" in
  *'staging.py cutover '*) exit "$CUTOVER_EXIT" ;;
  *upgrade-mode*) printf 'normal\n' ;;
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
chmod +x "$STATE/bin/"*
export PATH="$STATE/bin:$PATH"
export CALLS="$STATE/calls" DELIVERY_ENVIRONMENT=staging HELM_NAMESPACE=far
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
  grep -q 'staging.py cutover ' "$CALLS"
  if [[ "$CUTOVER_EXIT" == 1 ]]; then
    if grep -q '^helm upgrade ' "$CALLS"; then echo 'Unrehearsed staging deployment ran'; exit 1; fi
  else
    grep -q '^helm upgrade .* -n far ' "$CALLS"
    if grep '^helm upgrade ' "$CALLS" | grep -Eq -- '--atomic|--install'; then
      echo 'Staging must not install or automatically revert schema-dependent images'; exit 1
    fi
    grep -q '^helm get hooks ' "$CALLS"
    grep -q '^kubectl exec -i -n far ' "$CALLS"
  fi
done
export HELM_NAMESPACE=farmer
: > "$CALLS"
if bash ci/deploy/deploy-rc.sh > "$STATE/output" 2>&1; then
  echo 'Cross-environment namespace accepted'; exit 1
fi
test ! -s "$CALLS"
echo "PASS: Bash $BASH_VERSION staging evidence, namespace and recovery sequencing"
