#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"
chmod +x .githooks/pre-commit .githooks/pre-push
git config --local core.hooksPath .githooks

printf 'Git hooks enabled: %s\n' "$(git config --local --get core.hooksPath)"
printf 'Pre-commit checks staged files; pre-push checks newly pushed history.\n'
