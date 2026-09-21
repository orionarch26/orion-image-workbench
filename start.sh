#!/usr/bin/env bash
set -euo pipefail
STUDIO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$STUDIO_ROOT"
if [[ ! -x ComfyUI/.venv/bin/python ]]; then
  echo "缺少 ComfyUI/.venv，请参阅 GUIDE.md 的环境恢复章节。" >&2
  exit 1
fi
if [[ $# -eq 0 ]]; then
  set -- ui
fi
exec ComfyUI/.venv/bin/python studio.py "$@"
