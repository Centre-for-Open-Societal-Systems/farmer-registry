#!/bin/sh
# Register this registry into IAM — the compose equivalent of the chart's
# `iam-register` post-install hook Job.
#
# Pushes the application tile plus its roles/permissions catalog (payload.json,
# 11 roles and 72 permissions, taken verbatim from the chart) to the IAM staff
# portal API. Until this succeeds IAM cannot translate a user's Keycloak client
# roles into registry permissions, so the portal loads with nothing granted.
#
# Authenticates as the per-release Keycloak client via client_credentials, which
# is why that client has service accounts enabled in the realm import.
set -eu

echo "Waiting for IAM at ${IAM_REGISTER_URL%/user-access/*}..."
until curl -sf --max-time 5 "${IAM_REGISTER_URL%/user-access/*}/ping" >/dev/null 2>&1; do
  echo "  waiting for iam..."
  sleep 5
done
echo "  iam is ready."

echo "Building registration payload for ${APP_MNEMONIC} -> ${APP_URL}"
sed -e "s|__APPLICATION_MNEMONIC__|${APP_MNEMONIC}|g" \
    -e "s|__APPLICATION_URL__|${APP_URL}|g" \
    -e "s|__APPLICATION_DESCRIPTION__|${APP_DESCRIPTION}|g" \
    /payload/payload.json > /tmp/body.json

echo "Requesting access token from ${TOKEN_URL}"
i=0
TOKEN=""
while [ "$i" -lt "${TOKEN_MAX_ATTEMPTS}" ]; do
  RESP=$(curl -s --max-time 10 -X POST "${TOKEN_URL}" \
    -d grant_type=client_credentials \
    -d client_id="${CLIENT_ID}" \
    --data-urlencode client_secret="${CLIENT_SECRET}" || true)
  TOKEN=$(printf '%s' "${RESP}" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
  if [ -n "${TOKEN}" ]; then break; fi
  echo "  token not ready (attempt ${i}); response: ${RESP}"
  i=$((i + 1))
  sleep 5
done
if [ -z "${TOKEN}" ]; then
  echo "ERROR: could not obtain access token"
  exit 1
fi
echo "  got access token."

echo "Registering application with IAM at ${IAM_REGISTER_URL}"
i=0
while [ "$i" -lt "${REGISTER_MAX_ATTEMPTS}" ]; do
  CODE=$(curl -s -o /tmp/out.json -w '%{http_code}' --max-time 30 \
    -X POST "${IAM_REGISTER_URL}" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    --data @/tmp/body.json || true)
  echo "  register HTTP ${CODE}: $(cat /tmp/out.json 2>/dev/null || true)"
  case "${CODE}" in
    2*)
      echo "Registration succeeded."
      exit 0
      ;;
  esac
  i=$((i + 1))
  sleep 5
done
echo "ERROR: registration failed after ${REGISTER_MAX_ATTEMPTS} attempts"
exit 1
