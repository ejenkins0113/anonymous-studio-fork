#!/usr/bin/env bash
set -euo pipefail

PORT_PROXY="${AUTH_PROXY_PORT:-8088}"
PORT_GUI="${TAIPY_GUI_PORT:-5000}"
PORT_REST="${TAIPY_REST_PORT:-5001}"
MAIN_LOG="${ANON_MAIN_LOG:-/tmp/anon_gui_main.log}"
REST_LOG="${ANON_REST_LOG:-/tmp/anon_gui_rest.log}"

echo "Listeners:"
ss -ltnp | rg ":${PORT_GUI}|:${PORT_REST}|:${PORT_PROXY}" || true

echo
echo "HTTP checks:"

check_url() {
  local name="$1"
  local url="$2"
  echo "== ${name} =="
  if ! curl -sSI "$url"; then
    echo "curl failed for $url"
  fi
  echo
}

check_url "GUI" "http://127.0.0.1:${PORT_GUI}/"
check_url "REST" "http://127.0.0.1:${PORT_REST}/"
check_url "Proxy" "http://localhost:${PORT_PROXY}/"

echo "Recent GUI log tail:"
tail -n 20 "$MAIN_LOG" 2>/dev/null || echo "No GUI log at $MAIN_LOG"

echo
echo "Recent REST log tail:"
tail -n 20 "$REST_LOG" 2>/dev/null || echo "No REST log at $REST_LOG"

echo
echo "Hint:"
echo "  If Proxy returns 302 with a Location header to Auth0, the auth entrypoint is working."
echo "  If GUI returns 200 but Proxy is broken, the issue is in oauth2-proxy/nginx/Auth0."
