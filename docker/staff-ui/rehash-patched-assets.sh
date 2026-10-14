#!/bin/sh
# Re-hash the static assets the Dockerfile's bundle patches changed.
#
# Every patch in the staff-ui stage edits a Next.js build artefact in place,
# under its original content-hashed filename. Next serves /_next/static with
# `Cache-Control: public, max-age=31536000, immutable`, so a browser that
# already holds the old file never asks for it again: a patch can be present
# on the server and absent from every returning user's tab until they hard
# refresh. (Observed with the intake photo upload fix -- the API never saw the
# upload call because the browser was still running the previous chunk.)
#
# Fix the cache key instead of the cache: give each changed asset a new hash
# derived from its patched content and rewrite every reference to the old one
# -- the client-reference manifests (`static/chunks/1017-<hash>.js`), the
# webpack runtime's chunk-id -> hash map (`1017:"<hash>"`), build manifests
# and CSS links. A plain page load then fetches the new filename.
#
# Expects /tmp/static.before, written before the first patch by the same
# `find ... md5sum | sort` invocation used below. Runs under BusyBox sh.
set -eu
cd /app/.next

find static -type f \( -name '*.js' -o -name '*.css' \) -exec md5sum {} + | sort > /tmp/static.after
# comm(1): lines only in .after = assets whose checksum changed (inputs sorted).
changed=$(comm -13 /tmp/static.before /tmp/static.after | awk '{print $2}')
if [ -z "$changed" ]; then
  echo "rehash: no static assets changed by patches"
  exit 0
fi

for f in $changed; do
  dir=$(dirname "$f"); base=$(basename "$f")
  ext="${base##*.}"; name="${base%.*}"
  case "$name" in
    *-*) stem="${name%-*}-"; old="${name##*-}" ;;   # static/chunks/1017-0ccdb54fa9c4edb1.js
    *)   stem="";            old="$name" ;;         # static/css/<hash>.css
  esac
  # Only rename content hashes (>= 8 hex chars); leave anything else as is.
  if ! expr "$old" : '[0-9a-f]\{8,\}$' >/dev/null; then
    echo "rehash: skip $f (no content hash in name)"
    continue
  fi
  new=$(md5sum "$f" | cut -c1-"${#old}")
  mv "$f" "$dir/$stem$new.$ext"
  grep -rl "$old" . | while read -r ref; do
    sed -i "s/$old/$new/g" "$ref"
  done
  echo "rehash: $f -> $dir/$stem$new.$ext"
done
