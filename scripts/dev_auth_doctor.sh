#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Repo: $ROOT_DIR"
echo

echo "Taipy binary:"
if [[ -x "$ROOT_DIR/.venv/bin/taipy" ]]; then
  echo "  ok: $ROOT_DIR/.venv/bin/taipy"
else
  echo "  missing: $ROOT_DIR/.venv/bin/taipy"
fi

echo
echo "Auth proxy env file:"
if [[ -f "$ROOT_DIR/deploy/auth-proxy/.env.auth-proxy" ]]; then
  echo "  ok: deploy/auth-proxy/.env.auth-proxy"
else
  echo "  missing: deploy/auth-proxy/.env.auth-proxy"
fi

echo
echo "Running stack checks:"
bash scripts/check_auth_stack.sh || true
