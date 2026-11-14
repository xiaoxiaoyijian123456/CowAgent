#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_VERSION="3.13"
NODE_MAJOR="24"

COW_DATA_DIR="${COW_DATA_DIR:-$HOME/.cow}"
COW_WORKSPACE_DIR="${COW_WORKSPACE_DIR:-$HOME/cow}"
COW_BACKUP_DIR="${COW_BACKUP_DIR:-$HOME/Backups/CowAgent}"
COW_LOG_DIR="${COW_LOG_DIR:-$HOME/Library/Logs/CowAgent}"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
SERVICE_LABEL="com.steven.cowagent"
BACKUP_LABEL="com.steven.cowagent.backup"
SERVICE_PLIST="$LAUNCH_AGENTS_DIR/$SERVICE_LABEL.plist"
BACKUP_PLIST="$LAUNCH_AGENTS_DIR/$BACKUP_LABEL.plist"

log() {
    printf '[native-macos] %s\n' "$*" >&2
}

fail() {
    log "ERROR: $*"
    exit 1
}

require_user() {
    [ "$(id -u)" -ne 0 ] || fail "run as the logged-in user, not root"
    [ "$(uname -s)" = "Darwin" ] || fail "this installer targets macOS"
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

ensure_directories() {
    mkdir -p "$COW_DATA_DIR" "$COW_WORKSPACE_DIR" "$COW_BACKUP_DIR" "$COW_LOG_DIR" "$LAUNCH_AGENTS_DIR"
    chmod 700 "$COW_DATA_DIR" "$COW_WORKSPACE_DIR" "$COW_BACKUP_DIR" "$COW_LOG_DIR"
    local data_file log_path
    for data_file in "$COW_DATA_DIR"/*; do
        [ -f "$data_file" ] && chmod 600 "$data_file"
    done
    for log_path in "$COW_LOG_DIR"/*.log; do
        [ -e "$log_path" ] && chmod 600 "$log_path"
    done
}

ensure_ffmpeg() {
    command -v ffmpeg >/dev/null 2>&1 && return
    require_command brew
    log "Installing ffmpeg via Homebrew"
    HOMEBREW_NO_AUTO_UPDATE=1 brew install ffmpeg
}

ensure_python_runtime() {
    require_command uv
    uv python install "$PYTHON_VERSION"
    if [ -d "$PROJECT_ROOT/.venv" ]; then
        "$PROJECT_ROOT/.venv/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)' \
            || fail "existing .venv is not Python 3.13; remove it and rerun"
        return
    fi
    uv venv --python "$PYTHON_VERSION" "$PROJECT_ROOT/.venv"
}

install_python_dependencies() {
    require_command uv
    uv pip install --python "$PROJECT_ROOT/.venv/bin/python" pip setuptools wheel
    uv pip install --python "$PROJECT_ROOT/.venv/bin/python" -r "$PROJECT_ROOT/requirements.txt"
    local optional_filtered="$PROJECT_ROOT/.venv/requirements-optional.noxunfei.txt"
    grep -v -E '^[[:space:]]*websocket-client[[:space:]]*==[[:space:]]*1\.2\.0' \
        "$PROJECT_ROOT/requirements-optional.txt" > "$optional_filtered"
    uv pip install --python "$PROJECT_ROOT/.venv/bin/python" -r "$optional_filtered"
    uv pip install --python "$PROJECT_ROOT/.venv/bin/python" -e "$PROJECT_ROOT"
}

install_node_runtime() {
    require_command fnm
    fnm install "$NODE_MAJOR"
}

node_bin_dir() {
    local base="$HOME/.local/share/fnm/node-versions"
    local dirs=()
    local dir
    for dir in "$base"/v"$NODE_MAJOR".*/installation/bin; do
        [ -x "$dir/node" ] && dirs+=("$dir")
    done
    if [ "${#dirs[@]}" -eq 0 ]; then
        return 0
    fi
    printf '%s\n' "${dirs[@]}" | sort -V | tail -n 1
}

install_browser_runtime() {
    local browsers_dir="$COW_DATA_DIR/ms-playwright"
    local legacy_dir="$PROJECT_ROOT/ms-playwright"

    if [ -d "$legacy_dir" ] && [ ! -e "$browsers_dir" ]; then
        log "Migrating Playwright browsers to $browsers_dir"
        mv "$legacy_dir" "$browsers_dir"
    fi

    COW_DATA_DIR="$COW_DATA_DIR" \
    PLAYWRIGHT_BROWSERS_PATH="$browsers_dir" \
    PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST:-https://registry.npmmirror.com/-/binary/playwright}" \
        "$PROJECT_ROOT/.venv/bin/cow" install-browser
}

bootstrap_config() {
    "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/bootstrap_native_config.py"
}

setup_runtime_env() {
    local node_bin
    node_bin="$(node_bin_dir)"
    [ -n "$node_bin" ] || fail "Node $NODE_MAJOR LTS is not installed via fnm"
    export COW_DATA_DIR="$COW_DATA_DIR"
    export COW_DEPLOYMENT=managed
    export COW_NO_OPEN_BROWSER=1
    export PYTHONUNBUFFERED=1
    export PATH="$PROJECT_ROOT/.venv/bin:$node_bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
}

render_launchd_plists() {
    mkdir -p "$LAUNCH_AGENTS_DIR" "$COW_LOG_DIR"
    sed -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" -e "s|__HOME__|$HOME|g" \
        "$PROJECT_ROOT/scripts/launchd/com.steven.cowagent.plist.template" > "$SERVICE_PLIST"
    sed -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" -e "s|__HOME__|$HOME|g" \
        "$PROJECT_ROOT/scripts/launchd/com.steven.cowagent.backup.plist.template" > "$BACKUP_PLIST"
    chmod 600 "$SERVICE_PLIST" "$BACKUP_PLIST"
    plutil -lint "$SERVICE_PLIST" >/dev/null
    plutil -lint "$BACKUP_PLIST" >/dev/null
}

unload_services() {
    launchctl bootout "gui/$(id -u)/$SERVICE_LABEL" >/dev/null 2>&1 || true
    launchctl bootout "gui/$(id -u)/$BACKUP_LABEL" >/dev/null 2>&1 || true
    local attempt
    for attempt in $(seq 1 10); do
        if ! launchctl print "gui/$(id -u)/$SERVICE_LABEL" >/dev/null 2>&1 \
            && ! launchctl print "gui/$(id -u)/$BACKUP_LABEL" >/dev/null 2>&1; then
            return
        fi
        sleep 1
    done
    fail "launchd services did not unload within 10 seconds"
}

bootstrap_service() {
    local plist_path="$1"
    local label="$2"
    local attempt
    for attempt in $(seq 1 10); do
        if launchctl bootstrap "gui/$(id -u)" "$plist_path" >/dev/null 2>&1; then
            return
        fi
        sleep 1
    done
    fail "could not load launchd service $label after 10 attempts"
}

bootstrap_services() {
    render_launchd_plists
    unload_services
    bootstrap_service "$SERVICE_PLIST" "$SERVICE_LABEL"
    launchctl enable "gui/$(id -u)/$SERVICE_LABEL"
    launchctl kickstart -k "gui/$(id -u)/$SERVICE_LABEL"
    bootstrap_service "$BACKUP_PLIST" "$BACKUP_LABEL"
    launchctl enable "gui/$(id -u)/$BACKUP_LABEL"
}

wait_for_health() {
    local attempt
    for attempt in $(seq 1 60); do
        if curl -fsS --max-time 2 http://127.0.0.1:9899/api/health >/dev/null 2>&1; then
            log "CowAgent health check passed"
            return
        fi
        sleep 1
    done
    fail "CowAgent did not become healthy within 60 seconds; see $COW_LOG_DIR"
}
