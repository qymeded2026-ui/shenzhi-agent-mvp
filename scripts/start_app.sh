#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
STREAMLIT_BIN="${PROJECT_DIR}/.venv/bin/streamlit"

if [[ ! -x "${STREAMLIT_BIN}" ]]; then
    echo "未找到虚拟环境：${PROJECT_DIR}/.venv"
    echo "请先按照 README.md 完成环境安装。"
    exit 1
fi

cd "${PROJECT_DIR}"
"${STREAMLIT_BIN}" run app.py "$@"
