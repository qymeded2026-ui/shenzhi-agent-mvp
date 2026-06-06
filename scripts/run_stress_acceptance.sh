#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "未找到虚拟环境：${PYTHON_BIN}"
    echo "请在桌面 shenzhi_agent_mvp 项目中运行此脚本。"
    exit 1
fi

cd "${PROJECT_DIR}"
mkdir -p reports
"${PYTHON_BIN}" tests/stress_acceptance.py --report-dir "${PROJECT_DIR}/reports"
