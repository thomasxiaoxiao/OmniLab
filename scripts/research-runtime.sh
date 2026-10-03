#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export OMNIGENT_DATA_DIR="${OMNIGENT_DATA_DIR:-$PWD/.runtime/omnigent}"
mkdir -p "$OMNIGENT_DATA_DIR"
# Prefer an explicit binary. On macOS the desktop app can be newer than Homebrew.
if [[ -z "${OMNIGENT_CODEX_PATH:-}" ]]; then
  if [[ -x /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex ]]; then
    export OMNIGENT_CODEX_PATH=/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex
  else
    export OMNIGENT_CODEX_PATH="$(command -v codex)"
  fi
fi
export PATH="$(dirname "$OMNIGENT_CODEX_PATH"):$PATH"
export HARNESS_CODEX_MINIMAL_CONFIG=1
export HARNESS_CODEX_ENABLE_WEB_SEARCH=0
export HARNESS_CODEX_DISABLE_NATIVE_TOOLS=1
case "${1:-status}" in
  server)
    exec .venv/bin/omnigent server --host 127.0.0.1 --port 6767 --agent agents/local --no-open
    ;;
  host)
    exec .venv/bin/omnigent host http://127.0.0.1:6767 --no-open --non-interactive
    ;;
  status)
    "$OMNIGENT_CODEX_PATH" login status
    .venv/bin/python - <<'PY'
import httpx, json
from pathlib import Path
url = 'http://127.0.0.1:6767'
hosts = httpx.get(url + '/v1/hosts', timeout=10).raise_for_status().json()['hosts']
ready = [h for h in hosts if h['status'] == 'online' and h['configured_harnesses'].get('codex') is True]
if len(ready) != 1:
    raise SystemExit('Expected exactly one online Codex-ready host; check server and host terminals.')
host = ready[0]['host_id']
Path('.runtime/research.env').write_text(f'OMNIGENT_SERVER_URL={url}\nOMNIGENT_HOST_ID={host}\n')
print(json.dumps({'server': url, 'host_id': host, 'codex_ready': True,
                  'note': 'Readiness is not proof of completed inference.'}, indent=2))
PY
    ;;
  *) echo 'Usage: bash scripts/research-runtime.sh server|host|status' >&2; exit 2 ;;
esac
