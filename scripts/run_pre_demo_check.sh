#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_DIR}"
echo "== 1/3 系统自检与诊断包 =="
"${SCRIPT_DIR}/run_health_check.sh"
echo
echo "== 2/3 自动化回归测试 =="
"${SCRIPT_DIR}/run_regression_tests.sh"
echo
echo "== 3/3 稳定性验收 1.3 压力测试 =="
"${SCRIPT_DIR}/run_stress_acceptance.sh"
echo
echo "演示前自动检查已完成。请继续查看 docs/stability/演示前人工验收清单.md"
