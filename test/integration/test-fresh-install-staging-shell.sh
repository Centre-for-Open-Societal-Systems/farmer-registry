#!/usr/bin/env bash
# Exercise the staging fresh-install script with fake tools; no cluster, SSH or Docker access.
# Checks the order that matters: the pg_dump archive is written and verified on the backup target
# before the release is uninstalled, the databases are dropped only after the uninstall, and the
# install comes last. Also checks the refusals: no fresh dump while something exists, legacy
# databases, unpinned values, a bad backup target.
set -euo pipefail
TEST_ROOT=$(mktemp -d)
trap 'rm -rf "$TEST_ROOT"' EXIT
mkdir "$TEST_ROOT/bin"
cat > "$TEST_ROOT/bin/docker" <<'MOCK'
#!/bin/sh
printf 'docker %s\n' "$*" >> "$CALLS"
case "$*" in
  *'staging.py mode'*) printf '%s
' "${TEST_MODE:-upgrade}" ;;
  *'oan_chart.py values-url'*)
    [ "${TEST_VALUES_UNPINNED:-0}" -eq 0 ] || exit 1
    printf 'https://approved.example/farmer.yaml %s\n' "$(printf 'values' | sha256sum | cut -d ' ' -f 1)" ;;
  *'oan_chart.py url'*) printf 'https://approved.example/chart.tgz\n' ;;
esac
MOCK
cat > "$TEST_ROOT/bin/curl" <<'MOCK'
#!/bin/sh
out=''
while [ $# -gt 0 ]; do
  if [ "$1" = --output ]; then out=$2; fi
  shift
done
case "$out" in *environment-values.yaml) printf 'values' > "$out" ;; esac
exit 0
MOCK
cat > "$TEST_ROOT/bin/python3" <<'MOCK'
#!/bin/sh
printf 'python3 %s\n' "$*" >> "$CALLS"
MOCK
cat > "$TEST_ROOT/bin/helm" <<'MOCK'
#!/bin/sh
printf 'helm %s\n' "$*" >> "$CALLS"
if [ "$1" = status ]; then
  # After the install the release exists whatever it was before.
  if [ -f "$CALLS.installed" ]; then exit 0; fi
  exit "${TEST_RELEASE_PRESENT_EXIT:-1}"
fi
if [ "$1" = install ]; then : > "$CALLS.installed"; exit "${TEST_INSTALL_EXIT:-0}"; fi
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
    : > "$target"
    if [ "${TEST_DATABASES_PRESENT:-0}" -eq 1 ]; then
      for db in "$REGISTRY_DB" "$IDGEN_DB"; do
        printf '%s  ./%s.dump\n' "$(printf 'dump-%s' "$db" | sha256sum | cut -d ' ' -f 1)" "$db"
      done > "$target"
    fi ;;
  'cp -n farmer archive-pod:/tmp/'*)
    target=$(printf '%s' "$*" | sed 's/.* //')
    name=$(basename "$target" .dump)
    printf 'dump-%s' "$name" > "$target" ;;
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
printf 'backup@backup.example\n/srv/backups/farmer\nbackup.example ssh-ed25519 AAAAtest\n' > "$TEST_ROOT/target"
export PATH="$TEST_ROOT/bin:$PATH"
export KUBECONFIG="$TEST_ROOT/unused-kubeconfig" BACKUP_SSH_KEY="$TEST_ROOT/unused-key" BACKUP_TARGET_FILE="$TEST_ROOT/target"
export STAGING_EVIDENCE_FILE="$TEST_ROOT/evidence.json"
export HELM_RELEASE=farmer-registry HELM_NAMESPACE=farmer DELIVERY_ENVIRONMENT=staging
export ECR_REGISTRY=recorded-in-protected-evidence IMAGE_TAG=abcdef012345 SOURCE_COMMIT=abcdef012345abcdef012345abcdef012345abcd
export REGISTRY_DB=farmer_registry IDGEN_DB=farmer_registry_idgen
export CALLS="$TEST_ROOT/calls"
export DELIVERY_ACTION=fresh-install

run() {
  : > "$CALLS"
  rm -f "$CALLS.installed"
  result=0
  if [ "${NO_BACKUP:-0}" -eq 1 ]; then
    env -u BACKUP_SSH_KEY -u BACKUP_TARGET_FILE bash ci/deploy/fresh-install-staging.sh > "$TEST_ROOT/output" 2>&1 || result=$?
  else
    bash ci/deploy/fresh-install-staging.sh > "$TEST_ROOT/output" 2>&1 || result=$?
  fi
}
line_of() { grep -n -- "$1" "$CALLS" | head -n 1 | cut -d: -f1; }
# The cleanup trap may delete the (absent) archive Job; that is not a tool run of the install.
tools_ran() { grep -v '^kubectl delete job' "$CALLS" | grep -q '^helm \|^kubectl \|^ssh '; }
no_destruction() {
  if grep -q '^helm uninstall\|DROP DATABASE\|^helm install' "$CALLS"; then echo "$1"; exit 1; fi
}

# 1. Existing release and databases: archive, uninstall, drop, install in that order.
export TEST_RELEASE_PRESENT_EXIT=0 TEST_DATABASES_PRESENT=1
run
if [ "$result" -ne 0 ]; then cat "$TEST_ROOT/output"; exit 1; fi
archive=$(line_of 'ssh .*tee /srv/backups/farmer/')
uninstall=$(line_of 'helm uninstall farmer-registry -n farmer')
drop=$(line_of 'DROP DATABASE IF EXISTS "farmer_registry" WITH (FORCE)')
install=$(line_of 'helm install farmer-registry')
test -n "$archive" && test -n "$uninstall" && test -n "$drop" && test -n "$install"
test "$archive" -lt "$uninstall" && test "$uninstall" -lt "$drop" && test "$drop" -lt "$install"
grep -q 'DROP DATABASE IF EXISTS "farmer_registry_idgen" WITH (FORCE)' "$CALLS"
grep -q 'helm install .*--wait --wait-for-jobs --timeout 30m --post-renderer ci/deploy/oan-renderer.sh' "$CALLS"
grep -q 'oan_chart.py require-deployable staging' "$CALLS"
grep -q 'staging.py cluster ' "$CALLS"
grep -q 'deployment.py prepare-fresh ' "$CALLS"
grep -q 'deployment.py validate-fresh ' "$CALLS"
grep -q 'python3 scripts/operations/commons/check_seed_metadata.py .*90_checks.sql' "$CALLS"
grep -q 'ssh .*StrictHostKeyChecking=yes' "$CALLS"
if grep -q '^helm upgrade' "$CALLS"; then echo 'Fresh install must not upgrade'; exit 1; fi
if grep -Eq '_far([ "]|$)' "$CALLS"; then echo 'Legacy far databases must not be referenced'; exit 1; fi
# the chart is verified and the values fetched before any backup or removal
values=$(line_of 'oan_chart.py values-url')
test "$values" -lt "$archive"
echo "PASS: values, archive, uninstall, drop, install in order"

# 2. True first install: nothing exists, nothing to archive, install proceeds.
export TEST_RELEASE_PRESENT_EXIT=1 TEST_DATABASES_PRESENT=0
run
if [ "$result" -ne 0 ]; then cat "$TEST_ROOT/output"; exit 1; fi
if grep -q '^helm uninstall' "$CALLS"; then echo 'Nothing to uninstall on a first install'; exit 1; fi
grep -q '^helm install farmer-registry' "$CALLS"
echo 'PASS: first install without release or databases'

# 3. A release exists but no database could be dumped: refuse.
export TEST_RELEASE_PRESENT_EXIT=0 TEST_DATABASES_PRESENT=0
run
test "$result" -ne 0
no_destruction 'A release without a fresh dump must not be removed'
echo 'PASS: release without a dump is refused'

# 4. Corrupt archive on the target stops before removal.
export TEST_RELEASE_PRESENT_EXIT=0 TEST_DATABASES_PRESENT=1 TEST_ARCHIVE_CORRUPT=1
run
test "$result" -ne 0
no_destruction 'A bad archive must stop before removal'
unset TEST_ARCHIVE_CORRUPT
echo 'PASS: corrupt archive stops before uninstall'

# 5. Only the explicit action runs this script.
DELIVERY_ACTION=deploy run
test "$result" -ne 0
if tools_ran; then echo 'Other actions must stop before any tool runs'; exit 1; fi
echo 'PASS: only fresh-install runs this script'

# 6. Wrong namespace, legacy databases, unpinned values and bad targets stop before any change.
HELM_NAMESPACE=far run
test "$result" -ne 0
if tools_ran; then echo 'The legacy namespace must be refused first'; exit 1; fi
export TEST_VALUES_UNPINNED=1
run
test "$result" -ne 0
no_destruction 'Unpinned environment values must stop the install'
if grep -q '^ssh ' "$CALLS"; then echo 'Nothing may be archived before the values are pinned'; exit 1; fi
unset TEST_VALUES_UNPINNED
printf 'not a host\n/srv/backups\nkey\n' > "$TEST_ROOT/target"
run
test "$result" -ne 0
if tools_ran; then echo 'A malformed backup target must be refused first'; exit 1; fi
echo 'PASS: namespace, pin and target gates'

# 7. Install failure reports history and a classified diagnosis.
printf 'backup@backup.example\n/srv/backups/farmer\nbackup.example ssh-ed25519 AAAAtest\n' > "$TEST_ROOT/target"
export TEST_INSTALL_EXIT=1
run
test "$result" -ne 0
grep -q '^helm history ' "$CALLS"
grep -q 'docker .* diagnose ' "$CALLS"
echo 'PASS: install failure reports history and a classified diagnosis'

# 8. First-install evidence on an empty target: no backup credentials are bound, nothing is
#    archived, the log says so, and the install proceeds.
unset TEST_INSTALL_EXIT
export TEST_MODE=first-install NO_BACKUP=1 TEST_RELEASE_PRESENT_EXIT=1 TEST_DATABASES_PRESENT=0
run
if [ "$result" -ne 0 ]; then cat "$TEST_ROOT/output"; exit 1; fi
grep -q 'nothing to archive; the backup credentials are not used' "$TEST_ROOT/output"
if grep -q '^ssh ' "$CALLS"; then echo 'A first install must not touch the backup target'; exit 1; fi
grep -q 'staging.py mode' "$CALLS"
grep -q '^helm install farmer-registry' "$CALLS"
echo 'PASS: first install needs no backup credentials and says so'

# 9. First-install evidence never replaces anything: an existing database or release stops it
#    before the archive, the uninstall, the drop or the install, with or without credentials.
for no_backup in 1 0; do
  export NO_BACKUP=$no_backup
  export TEST_RELEASE_PRESENT_EXIT=1 TEST_DATABASES_PRESENT=1
  run
  test "$result" -ne 0
  no_destruction 'First-install evidence must not replace existing databases'
  if grep -q '^ssh ' "$CALLS"; then echo 'Nothing may be archived under first-install evidence'; exit 1; fi
  grep -q 'First-install evidence, but a release or a target database already exists' "$TEST_ROOT/output"
  export TEST_RELEASE_PRESENT_EXIT=0 TEST_DATABASES_PRESENT=0
  run
  test "$result" -ne 0
  no_destruction 'First-install evidence must not remove an existing release'
done
echo 'PASS: first-install evidence refuses an existing release or database'

# 10. The full evidence shape still demands the backup credentials, before any cluster change.
export TEST_MODE=upgrade NO_BACKUP=1 TEST_RELEASE_PRESENT_EXIT=1 TEST_DATABASES_PRESENT=0
run
test "$result" -ne 0
grep -q 'bind the backup SSH key and target credentials' "$TEST_ROOT/output"
if grep -q '^kubectl apply\|^helm ' "$CALLS"; then echo 'Missing backup credentials must stop before the archive Job'; exit 1; fi
# a lone credential is a configuration error, not a silent skip
NO_BACKUP=0 run
BACKUP_TARGET_FILE_SAVE=$BACKUP_TARGET_FILE
result=0
: > "$CALLS"
env -u BACKUP_SSH_KEY BACKUP_TARGET_FILE="$BACKUP_TARGET_FILE_SAVE" bash ci/deploy/fresh-install-staging.sh > "$TEST_ROOT/output" 2>&1 || result=$?
test "$result" -ne 0
if tools_ran; then echo 'A half-bound backup credential must be refused first'; exit 1; fi
unset TEST_MODE NO_BACKUP
echo 'PASS: the upgrade shape still needs the backup credentials'
