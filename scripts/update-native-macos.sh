#!/bin/bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=scripts/native-macos-common.sh
. "$PROJECT_ROOT/scripts/native-macos-common.sh"

require_user
require_command git
cd "$PROJECT_ROOT"
old_sha="$(git rev-parse --verify HEAD)"

on_error() {
    local status=$?
    trap - ERR
    set +e
    log "Update failed; restoring $old_sha"
    git reset --hard "$old_sha"
    ensure_python_runtime
    install_python_dependencies
    bootstrap_services
    wait_for_health
    exit "$status"
}
trap on_error ERR

unload_services
git pull --ff-only
ensure_python_runtime
install_python_dependencies
install_node_runtime
ensure_ffmpeg
install_browser_runtime
bootstrap_config
bootstrap_services
wait_for_health
trap - ERR

log "Update complete: $(git rev-parse --short HEAD)"
