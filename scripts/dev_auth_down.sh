#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WITH_PROXY=0

usage() {
  cat <<'EOF'
Usage:
  scripts/dev_auth_down.sh [--with-proxy]

Options:
  --with-proxy  Also stop the auth proxy Docker stack.

Default behavior:
  - kills anything listening on 5000 and 5001
  - removes saved pid files from /tmp if present
EOF
}

while (($#)); do
  case "$1" in
    --with-proxy)
      WITH_PROXY=1
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

echo "Stopping anything on 5000/5001..."
fuser -k 5000/tcp 2>/dev/null || true
fuser -k 5001/tcp 2>/dev/null || true
rm -f /tmp/anon_gui_main.pid /tmp/anon_gui_rest.pid

if (( WITH_PROXY )); then
  echo "Stopping auth proxy stack..."
  make auth-proxy-down
fi

echo "Remaining listeners:"
ss -ltnp | rg ':5000|:5001|:8088' || true
