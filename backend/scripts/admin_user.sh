#!/usr/bin/env bash
# Convenience wrapper for scripts/create_user.py — activates the venv and forwards
# everything through. Run from anywhere, e.g.:
#   backend/scripts/admin_user.sh --email doc@example.com --full-name "Dr. X" --role physician
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

cd "$BACKEND_DIR"
. .venv/bin/activate
exec python scripts/create_user.py "$@"
