#!/usr/bin/env sh
set -eu
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

SELECTED_PY=""
for cand in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >/dev/null 2>&1; then
      SELECTED_PY="$(command -v "$cand")"
      break
    fi
  fi
done

if [ -z "$SELECTED_PY" ]; then
  echo "Error: Python 3.11+ is required (all discovered python binaries were older than 3.11 or missing)." >&2
  exit 1
fi

exec "$SELECTED_PY" "$SCRIPT_DIR/install.py" "$@"
