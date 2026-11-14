#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=scripts/native-macos-common.sh
. "$PROJECT_ROOT/scripts/native-macos-common.sh"

setup_runtime_env
exec "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/native_maintenance.py"
