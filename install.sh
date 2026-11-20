#!/usr/bin/env sh
set -eu
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
else
  echo "Error: Python 3.11+ is required." >&2
  exit 1
fi
exec "$PY" "$SCRIPT_DIR/install.py" "$@"
