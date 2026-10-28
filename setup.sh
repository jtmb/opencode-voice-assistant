#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$(readlink -f -- "$0")")"
DEV=0
MODEL_ARGS=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --dev) DEV=1; shift ;;
        --reuse-models) MODEL_ARGS=(--reuse-models "$2"); shift 2 ;;
        *) echo "Usage: ./setup.sh [--dev] [--reuse-models DIR]" >&2; exit 1 ;;
    esac
done
for program in uv npm python3 bwrap pw-cli pw-cat pw-dump; do
    command -v "$program" >/dev/null || { echo "Missing program: $program" >&2; exit 1; }
done
export UV_CACHE_DIR="$PWD/.cache/uv" UV_LINK_MODE=copy
uv venv --python /usr/bin/python3 --allow-existing .venv
LOCK=requirements.lock.txt
if [ "$DEV" -eq 1 ]; then LOCK=requirements-dev.lock.txt; fi
uv pip install --python .venv/bin/python -r "$LOCK"
npm ci --ignore-scripts --no-audit --no-fund
python3 scripts/download_models.py "${MODEL_ARGS[@]}"
chmod +x scripts/audio-worker.sh
echo 'Speech dependencies ready. See README.md to register the TUI plugin.'
