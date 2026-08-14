#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/app.py" ]]; then
  PROJECT_ROOT="$SCRIPT_DIR"
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

"$SCRIPT_DIR/bootstrap_macos.sh"
exec "$SCRIPT_DIR/.venv/bin/python" "$PROJECT_ROOT/app.py"
