#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_ACTIVATE="$ROOT_DIR/.venv/bin/activate"
TAIPY_BIN="$ROOT_DIR/.venv/bin/taipy"
MAIN_LOG="${ANON_MAIN_LOG:-/tmp/anon_gui_main.log}"
REST_LOG="${ANON_REST_LOG:-/tmp/anon_gui_rest.log}"

WITH_PROXY=0
MEMORY_MODE=1

usage() {
  cat <<'EOF'
Usage:
  scripts/dev_auth_stack.sh [--with-proxy] [--no-memory]

Options:
  --with-proxy  Start the auth proxy Docker stack via `make auth-proxy-up`.
  --no-memory   Do not force test-safe in-memory settings for GUI/REST.

Default behavior:
  - kills anything listening on 5000 and 5001
  - starts GUI on 5000
  - starts REST on 5001
  - writes logs to /tmp/anon_gui_main.log and /tmp/anon_gui_rest.log
  - forces memory-backed local mode unless --no-memory is passed
EOF
}

while (($#)); do
  case "$1" in
    --with-proxy)
      WITH_PROXY=1
      ;;
    --no-memory)
      MEMORY_MODE=0
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
  shift
done

if [[ ! -f "$VENV_ACTIVATE" || ! -x "$TAIPY_BIN" ]]; then
  echo "Expected Taipy venv not found at $ROOT_DIR/.venv" >&2
  exit 1
fi

echo "Stopping anything on 5000/5001..."
fuser -k 5000/tcp 2>/dev/null || true
fuser -k 5001/tcp 2>/dev/null || true

if (( WITH_PROXY )); then
  echo "Starting auth proxy stack..."
  make auth-proxy-up
fi

COMMON_ENV=()
if (( MEMORY_MODE )); then
  COMMON_ENV+=(
    "ANON_MODE=development"
    "ANON_STORE_BACKEND=memory"
    "ANON_RAW_INPUT_BACKEND=memory"
  )
fi

echo "Starting GUI on 5000..."
(
  source "$VENV_ACTIVATE"
  env "${COMMON_ENV[@]}" ANON_GUI_USE_RELOADER=0 ANON_GUI_DEBUG=0 \
    nohup "$TAIPY_BIN" run --host 0.0.0.0 main.py >"$MAIN_LOG" 2>&1 < /dev/null &
  echo $! > /tmp/anon_gui_main.pid
)

echo "Starting REST on 5001..."
(
  source "$VENV_ACTIVATE"
  env "${COMMON_ENV[@]}" TAIPY_PORT=5001 TAIPY_HOST=0.0.0.0 \
    nohup "$TAIPY_BIN" run rest_main.py >"$REST_LOG" 2>&1 < /dev/null &
  echo $! > /tmp/anon_gui_rest.pid
)

# Wait up to 15s for both ports to bind
echo "Waiting for ports 5000 and 5001..."
for port in 5000 5001; do
  deadline=$(( SECONDS + 15 ))
  while ! ss -tlnp | grep -q ":${port} "; do
    if (( SECONDS >= deadline )); then
      echo "  WARNING: port $port did not bind within 15s" >&2
      break
    fi
    sleep 0.5
  done
done

echo
echo "Listeners:"
ss -ltnp | grep -E ':5000|:5001|:8088' || true

echo
echo "GUI log:  $MAIN_LOG"
echo "REST log: $REST_LOG"
echo
echo "Open:"
echo "  Direct GUI:  http://127.0.0.1:5000/"
echo "  Auth proxy:  http://localhost:8088/"
echo
echo "If the UI looks stale, use a private/incognito window or hard refresh."
