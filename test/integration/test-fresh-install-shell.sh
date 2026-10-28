#!/usr/bin/env bash
# Exercise the fresh-install script with fake tools; no cluster, SSH or Docker access.
# Checks the order that matters: the archive is written and verified on the box
# before the release is uninstalled, the databases are dropped only after the
# uninstall, and the install comes last.
set -euo pipefail
TEST_ROOT=$(mktemp -d)
trap 'rm -rf "$TEST_ROOT"' EXIT
mkdir "$TEST_ROOT/bin"
cat > "$TEST_ROOT/bin/docker" <<'MOCK'
#!/bin/sh
printf 'docker %s\n' "$*" >> "$CALLS"
case "$*" in
  *'oan_chart.py url'*) printf 'https://approved.example/chart.tgz\n' ;;
esac
MOCK
cat > "$TEST_ROOT/bin/curl" <<'MOCK'
#!/bin/sh
exit 0
MOCK
cat > "$TEST_ROOT/bin/helm" <<'MOCK'
#!/bin/sh
printf 'helm %s\n' "$*" >> "$CALLS"
if [ "$1" = install ]; then exit "${TEST_INSTALL_EXIT:-0}"; fi
MOCK
cat > "$TEST_ROOT/bin/kubectl" <<'MOCK'
#!/bin/sh
printf 'kubectl %s\n' "$*" >> "$CALLS"
case "$*" in
  'apply -f -') cat > /dev/null ;;
  'get pod -n farmer -l job-name='*' -o name') echo pod/archive-pod ;;
  'get pod -n farmer archive-pod -o jsonpath='*) echo Running ;;
  'cp -n farmer archive-pod:/tmp/SHA256SUMS '*)
    target=$(printf '%s' "$*" | sed 's/.* //')
    for db in "$REGISTRY_DB" "$IDGEN_DB"; do
      printf '%s  ./%s.dump\n' "$(printf 'dump-%s' "$db" | sha256sum | cut -d ' ' -f 1)" "$db"
    done > "$target" ;;
  'cp -n farmer archive-pod:/tmp/'*)
    target=$(printf '%s' "$*" | sed 's/.* //')
    name=$(basename "$target" .dump)
    printf 'dump-%s' "$name" > "$target" ;;
  *'psql'*) [ "${TEST_DROP_EXIT:-0}" -eq 0 ] || exit "$TEST_DROP_EXIT" ;;
esac
exit 0
MOCK
cat > "$TEST_ROOT/bin/ssh" <<'MOCK'
#!/bin/sh
printf 'ssh %s\n' "$*" >> "$CALLS"
case "$*" in
  *' | sha256sum') if [ "${TEST_ARCHIVE_CORRUPT:-0}" -eq 1 ]; then echo 'ffff -'; else sha256sum; fi ;;
  *) cat > /dev/null 2>&1 || true ;;
esac
exit 0
MOCK
chmod +x "$TEST_ROOT/bin/"*
export PATH="$TEST_ROOT/bin:$PATH"
export KUBECONFIG="$TEST_ROOT/unused-kubeconfig" BACKUP_SSH_KEY="$TEST_ROOT/unused-key"
export HELM_RELEASE=farmer-registry HELM_NAMESPACE=farmer
export ECR_REGISTRY=123456789012.dkr.ecr.ap-south-1.amazonaws.com IMAGE_TAG=abcdef012345
export CALLS="$TEST_ROOT/calls"

run() {
  : > "$CALLS"
  result=0
  bash ci/deploy/fresh-install-dev.sh > "$TEST_ROOT/output" 2>&1 || result=$?
}
line_of() { grep -n -- "$1" "$CALLS" | head -n 1 | cut -d: -f1; }

export DELIVERY_ACTION=fresh-install
run
if [ "$result" -ne 0 ]; then cat "$TEST_ROOT/output"; exit 1; fi
archive=$(line_of 'ssh .*sudo -n tee /var/backups/oan/farmer/')
uninstall=$(line_of 'helm uninstall farmer-registry -n farmer')
drop=$(line_of 'DROP DATABASE IF EXISTS "farmer_registry" WITH (FORCE)')
install=$(line_of 'helm install farmer-registry')
test -n "$archive" && test -n "$uninstall" && test -n "$drop" && test -n "$install"
test "$archive" -lt "$uninstall" && test "$uninstall" -lt "$drop" && test "$drop" -lt "$install"
grep -q 'DROP DATABASE IF EXISTS "farmer_registry_idgen" WITH (FORCE)' "$CALLS"
grep -q 'helm install .*--wait --wait-for-jobs --timeout 30m --post-renderer ci/deploy/oan-renderer.sh' "$CALLS"
grep -q 'docker .*oan_chart.py require-deployable dev' "$CALLS"
grep -q 'docker .*deployment.py prepare ' "$CALLS"
if grep -q '^helm upgrade' "$CALLS"; then echo 'Fresh install must not upgrade'; exit 1; fi
echo "PASS: archive, uninstall, drop, install in order"

export DELIVERY_ACTION=deploy
run
test "$result" -ne 0
if grep -q '^helm \|^kubectl \|^ssh ' "$CALLS"; then echo 'Other actions must stop before any tool runs'; exit 1; fi
echo 'PASS: only the explicit fresh-install action runs this script'

export DELIVERY_ACTION=fresh-install TEST_ARCHIVE_CORRUPT=1
run
test "$result" -ne 0
if grep -q '^helm uninstall\|DROP DATABASE' "$CALLS"; then echo 'A bad archive must stop before removal'; exit 1; fi
echo 'PASS: corrupt archive stops before uninstall'
unset TEST_ARCHIVE_CORRUPT

export TEST_INSTALL_EXIT=1
run
test "$result" -ne 0
grep -q '^helm history ' "$CALLS"
grep -q 'docker .* diagnose ' "$CALLS"
echo 'PASS: install failure reports history and a classified diagnosis'
