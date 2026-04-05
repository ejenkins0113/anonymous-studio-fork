#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

load_env_file() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" == *=* ]] || continue

    local key="${line%%=*}"
    local value="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"

    if [[ -z "${!key:-}" ]]; then
      export "${key}=${value}"
    fi
  done < "$env_file"
}

load_env_file "$ROOT_DIR/.env"
load_env_file "$ROOT_DIR/deploy/auth-proxy/.env.auth-proxy"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/auth0_update_app.sh [--port 8088] [--app-client-id CLIENT_ID]

The script auto-loads values from:
  - .env
  - deploy/auth-proxy/.env.auth-proxy

Shell environment variables override file values.

Required environment variables:
  AUTH0_DOMAIN
  AUTH0_M2M_CLIENT_ID
  AUTH0_M2M_CLIENT_SECRET

Optional environment variables:
  AUTH0_APP_CLIENT_ID    Defaults to the anonymous-studio app client id
  AUTH0_PORT             Defaults to 8088

Examples:
  AUTH0_DOMAIN=dev-tenant.us.auth0.com \
  AUTH0_M2M_CLIENT_ID=... \
  AUTH0_M2M_CLIENT_SECRET=... \
  bash scripts/auth0_update_app.sh

  AUTH0_DOMAIN=dev-tenant.us.auth0.com \
  AUTH0_M2M_CLIENT_ID=... \
  AUTH0_M2M_CLIENT_SECRET=... \
  AUTH0_APP_CLIENT_ID=abc123 \
  bash scripts/auth0_update_app.sh --port 8088
EOF
}

PORT="${AUTH0_PORT:-${AUTH_PROXY_PORT:-8088}}"
APP_CLIENT_ID="${AUTH0_APP_CLIENT_ID:-${AUTH0_CLIENT_ID:-wurcUczBBZFgWH5xWOomOwa7ixwAPS0x}}"

while (($#)); do
  case "$1" in
    --port)
      PORT="${2:?missing value for --port}"
      shift 2
      ;;
    --app-client-id)
      APP_CLIENT_ID="${2:?missing value for --app-client-id}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

missing=()
[[ -n "${AUTH0_DOMAIN:-}" ]] || missing+=("AUTH0_DOMAIN")
[[ -n "${AUTH0_M2M_CLIENT_ID:-}" ]] || missing+=("AUTH0_M2M_CLIENT_ID")
[[ -n "${AUTH0_M2M_CLIENT_SECRET:-}" ]] || missing+=("AUTH0_M2M_CLIENT_SECRET")

if ((${#missing[@]})); then
  printf 'Missing required Auth0 settings: %s\n' "${missing[*]}" >&2
  cat >&2 <<'EOF'

Looked in:
  - current shell environment
  - .env
  - deploy/auth-proxy/.env.auth-proxy

Notes:
  - AUTH0_DOMAIN and AUTH0_CLIENT_ID can come from deploy/auth-proxy/.env.auth-proxy
  - AUTH0_M2M_CLIENT_ID and AUTH0_M2M_CLIENT_SECRET must belong to a Machine-to-Machine
    application authorized for the Auth0 Management API
EOF
  exit 1
fi

CALLBACK_URL="http://localhost:${PORT}/oauth2/callback"
LOGOUT_URL="http://localhost:${PORT}"
WEB_ORIGIN="http://localhost:${PORT}"
AUDIENCE="https://${AUTH0_DOMAIN}/api/v2/"

echo "Requesting Auth0 Management API token..."
TOKEN_JSON="$(
  curl -fsSL --request POST \
    --url "https://${AUTH0_DOMAIN}/oauth/token" \
    --header 'content-type: application/json' \
    --data "{\"client_id\":\"${AUTH0_M2M_CLIENT_ID}\",\"client_secret\":\"${AUTH0_M2M_CLIENT_SECRET}\",\"audience\":\"${AUDIENCE}\",\"grant_type\":\"client_credentials\"}"
)"

ACCESS_TOKEN="$(
  TOKEN_JSON="$TOKEN_JSON" python3 - <<'PY'
import json, os, sys
data = json.loads(os.environ["TOKEN_JSON"])
token = data.get("access_token", "")
if not token:
    raise SystemExit("missing access_token in Auth0 token response")
print(token)
PY
)"

PATCH_BODY="$(
  CALLBACK_URL="$CALLBACK_URL" LOGOUT_URL="$LOGOUT_URL" WEB_ORIGIN="$WEB_ORIGIN" python3 - <<'PY'
import json, os
print(json.dumps({
    "callbacks": [os.environ["CALLBACK_URL"]],
    "allowed_logout_urls": [os.environ["LOGOUT_URL"]],
    "web_origins": [os.environ["WEB_ORIGIN"]],
}))
PY
)"

echo "Updating application ${APP_CLIENT_ID} to use localhost:${PORT}..."
curl -fsSL --request PATCH \
  --url "https://${AUTH0_DOMAIN}/api/v2/clients/${APP_CLIENT_ID}" \
  --header "authorization: Bearer ${ACCESS_TOKEN}" \
  --header 'content-type: application/json' \
  --data "${PATCH_BODY}" >/dev/null

echo "Verifying application settings..."
VERIFY_JSON="$(
  curl -fsSL --request GET \
    --url "https://${AUTH0_DOMAIN}/api/v2/clients/${APP_CLIENT_ID}" \
    --header "authorization: Bearer ${ACCESS_TOKEN}"
)"

VERIFY_JSON="$VERIFY_JSON" python3 - <<'PY'
import json, os
data = json.loads(os.environ["VERIFY_JSON"])
summary = {
    "client_id": data.get("client_id"),
    "callbacks": data.get("callbacks", []),
    "allowed_logout_urls": data.get("allowed_logout_urls", []),
    "web_origins": data.get("web_origins", []),
}
print(json.dumps(summary, indent=2))
PY
