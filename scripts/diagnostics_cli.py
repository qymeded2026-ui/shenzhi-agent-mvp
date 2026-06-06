import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from stability_diagnostics import (
    create_diagnostic_bundle,
    run_health_check,
    save_health_report,
)
from stability_store import ensure_periodic_backup


def main() -> int:
    parser = argparse.ArgumentParser(description="神志思训稳定性补丁 1.4 自检工具")
    parser.add_argument("--bundle", action="store_true", help="同时生成脱敏诊断包")
    args = parser.parse_args()

    backup_path = ensure_periodic_backup()
    report = run_health_check()
    report_path = save_health_report(report)
    summary = report["summary"]

    print("神志思训系统自检")
    print(f"总体状态：{summary['label']}")
    print(
        f"检查结果：通过 {summary['pass']} 项，提示 {summary['warn']} 项，异常 {summary['fail']} 项"
    )
    for check in report["checks"]:
        marker = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}[check["status"]]
        print(f"[{marker}] {check['name']}：{check['message']}")
    print(f"数据库备份：{backup_path}")
    print(f"自检报告：{report_path}")

    if args.bundle:
        print(f"诊断包：{create_diagnostic_bundle(report=report)}")
    return 1 if summary["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
