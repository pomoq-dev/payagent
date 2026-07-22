#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -z "${PYPI_TOKEN:-}" ]]; then
  echo "Set PYPI_TOKEN (pypi-…) or use GitHub Release + Trusted Publisher." >&2
  exit 1
fi
python -m pip install -U build twine
rm -rf dist
python -m build
python -m twine upload dist/* -u __token__ -p "$PYPI_TOKEN"
echo "Published. Verify: https://pypi.org/project/payagent/"
