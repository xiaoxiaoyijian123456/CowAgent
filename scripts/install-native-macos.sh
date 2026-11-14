#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=scripts/native-macos-common.sh
. "$PROJECT_ROOT/scripts/native-macos-common.sh"

umask 077
require_user
for command_name in uv fnm git curl gzip sed plutil; do
    require_command "$command_name"
done
ensure_directories
ensure_python_runtime
install_python_dependencies
install_node_runtime
ensure_ffmpeg
install_browser_runtime
bootstrap_config
bootstrap_services
wait_for_health

log "Installation complete"
printf 'Web console: http://127.0.0.1:9899/\n'
printf 'Data root: %s\n' "$COW_DATA_DIR"
printf 'Workspace: %s\n' "$COW_WORKSPACE_DIR"
printf 'Backups: %s\n' "$COW_BACKUP_DIR"
