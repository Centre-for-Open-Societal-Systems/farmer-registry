#!/usr/bin/env bash
# New Dev only. Routine builds read a receipt; resets require explicit mode.
set -euo pipefail
set +x
case "${DELIVERY_ENVIRONMENT:-${COSS_DEPLOY_ENVIRONMENT:-dev}}" in dev) ;; *) echo 'New Dev reset wrapper refuses other environments' >&2; exit 1 ;; esac
: "${REGISTRY_RESET_MANIFEST:?Bind the immutable reviewed first-install manifest}"
RESET_ACTION=${NEW_DEV_RESET_ACTION:-check}
case "$RESET_ACTION" in check|initialize|resume) ;; *) echo 'Invalid reset action' >&2; exit 1 ;; esac
python3 - "$REGISTRY_RESET_MANIFEST" "$RESET_ACTION" <<'PY'
import json,os,sys
from pathlib import Path
owner=json.loads(Path('ci/deploy/reset-owner.json').read_text())
config=json.loads(Path(sys.argv[1]).read_text())
profile=json.loads(Path('ci/deploy/oan-chart.json').read_text())
if owner['profileKey']:
    profile=profile[owner['profileKey']]
def require(ok,message):
    if not ok: raise SystemExit(message)
require(profile.get('promotionReady') is True and profile.get('environment')=='dev','Deployment blocked: refactor promotion acceptance is incomplete')
require(config.get('target',{}).get('registry')==owner['registry'],'Reset manifest belongs to a different registry')
require(config.get('epoch')==owner['epoch'],'Unexpected first-install epoch')
if sys.argv[2]!='check':
    source=os.environ.get('SOURCE_COMMIT') or os.environ.get('GIT_COMMIT')
    require(source and config.get('source_commit')==source,'Reset source differs from the verified build')
    expected=profile['name']+':'+profile['version']+'@sha256:'+profile['sha256']
    require(config.get('chart')==expected,'Reset chart differs from the immutable build profile')
PY
if [[ "$RESET_ACTION" == check ]]; then
  exec python3 ci/deploy/reset_new_dev.py "$REGISTRY_RESET_MANIFEST" --require-verified
fi
: "${REGISTRY_RESET_ADMIN_SERVICE:?Mount the reviewed libpq service and password files}"
if [[ "$RESET_ACTION" == initialize ]]; then
  exec python3 ci/deploy/reset_new_dev.py "$REGISTRY_RESET_MANIFEST" --execute --initialize-receipt --admin-service "$REGISTRY_RESET_ADMIN_SERVICE"
fi
exec python3 ci/deploy/reset_new_dev.py "$REGISTRY_RESET_MANIFEST" --execute --resume --admin-service "$REGISTRY_RESET_ADMIN_SERVICE"
