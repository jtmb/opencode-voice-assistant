#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$ROOT"
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 DO_NOT_TRACK=1 PYTHONDONTWRITEBYTECODE=1
exec bwrap --unshare-net --unshare-pid --bind / / --dev /dev --proc /proc --die-with-parent --chdir "$ROOT" \
    --setenv OPENCODE_VOICE_OFFLINE 1 -- .venv/bin/python -u -m audio.worker
