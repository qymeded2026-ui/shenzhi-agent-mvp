#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "未找到虚拟环境：${PYTHON_BIN}"
    exit 1
fi

cd "${PROJECT_DIR}"
"${PYTHON_BIN}" scripts/diagnostics_cli.py --bundle
