#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PROJECT_ROOT
export PM2_HOME="$PROJECT_ROOT/.runtime/pm2"
export DEPLOY_PYTHON="${DEPLOY_PYTHON:-$(command -v python3)}"
cd "$PROJECT_ROOT"
exec "$PROJECT_ROOT/node_modules/.bin/pm2" "$@"
