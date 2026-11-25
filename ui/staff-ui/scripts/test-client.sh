#!/usr/bin/env bash
# Run the client tests of the OAN overrides (tests/) inside the materialized
# .app/, against the pinned upstream packages. The test tools are installed into
# .app/node_modules only (npm --no-save: no change to .app/package.json or its
# lockfile, nothing global) and are reinstalled after `npm ci` removes them.
set -euo pipefail

ui_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
app_dir="$ui_root/.app"

[[ -f "$app_dir/package.json" ]] || { echo "Missing .app/: run npm install first" >&2; exit 1; }

if [[ ! -d "$app_dir/node_modules/vitest" || ! -d "$app_dir/node_modules/jsdom" || ! -d "$app_dir/node_modules/@testing-library/react" ]]; then
    ( cd "$app_dir" && npm install --no-save --no-audit --no-fund --loglevel=error \
        vitest@3.2.4 jsdom@26.1.0 @testing-library/react@16.3.0 @testing-library/dom@10.4.0 )
fi

cd "$app_dir"
exec npx vitest run --config ../vitest.config.mts "$@"
