import importlib.util
import json
import os
import platform
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional


BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = Path(os.getenv("SHENZHI_RUNTIME_DIR", BASE_DIR / "runtime"))
DIAGNOSTIC_DIR = RUNTIME_DIR / "diagnostics"
REPORT_DIR = BASE_DIR / "reports"
IMAGE_PATTERN = re.compile(r"^case_\d{3}\.(?:jpg|jpeg|png|webp)$", re.IGNORECASE)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _result(name: str, status: str, message: str, **details) -> Dict:
    return {
        "name": name,
        "status": status,
        "message": message,
        "details": details,
    }


def _case_image_paths(case: Dict) -> Iterable[str]:
    images = case.get("tcm_info", {}).get("tongue_images", [])
    return images if isinstance(images, list) else []


def _configured_api_key(project_root: Path) -> bool:
    secrets_path = project_root / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return False
    secrets_text = secrets_path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"DEEPSEEK_API_KEY\s*=\s*[\"']([^\"']+)[\"']", secrets_text)
    return bool(match and match.group(1).strip())


def _runtime_dir(project_root: Path) -> Path:
    return Path(os.getenv("SHENZHI_RUNTIME_DIR", project_root / "runtime"))


def _check_case_library(project_root: Path, expected_case_count: int) -> Dict:
    case_files = sorted((project_root / "cases").glob("*.json"))
    invalid_files: List[str] = []
    referenced_images: List[str] = []
    for case_file in case_files:
        try:
            case = json.loads(case_file.read_text(encoding="utf-8"))
            referenced_images.extend(_case_image_paths(case))
        except (OSError, json.JSONDecodeError):
            invalid_files.append(case_file.name)

    status = "pass"
    if invalid_files or len(case_files) != expected_case_count:
        status = "fail"
    return _result(
        "病例库",
        status,
        f"发现 {len(case_files)} 例病例，JSON 解析失败 {len(invalid_files)} 例。",
        expected=expected_case_count,
        found=len(case_files),
        invalid_files=invalid_files,
        referenced_images=referenced_images,
    )


def _check_tongue_images(project_root: Path, expected_case_count: int, cases_check: Dict) -> Dict:
    image_dir = project_root / "tongue_images"
    anonymized_images = sorted(
        path.name
        for path in image_dir.iterdir()
        if path.is_file() and IMAGE_PATTERN.match(path.name)
    ) if image_dir.exists() else []
    referenced_images = cases_check["details"].get("referenced_images", [])
    missing_references = sorted(
        image_path
        for image_path in referenced_images
        if not (project_root / image_path).exists()
    )
    status = "pass"
    if len(anonymized_images) != expected_case_count or missing_references:
        status = "fail"
    return _result(
        "舌象图片",
        status,
        f"匿名化舌象 {len(anonymized_images)} 张，缺失引用 {len(missing_references)} 张。",
        expected=expected_case_count,
        found=len(anonymized_images),
        missing_references=missing_references,
    )


def _check_runtime_storage(project_root: Path) -> Dict:
    runtime_dir = _runtime_dir(project_root)
    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=".write_check_",
            dir=runtime_dir,
            delete=True,
        ) as check_file:
            check_file.write(b"ok")
            check_file.flush()
        free_mb = round(shutil.disk_usage(runtime_dir).free / (1024 * 1024), 1)
        return _result(
            "运行目录",
            "pass",
            f"运行目录可写，可用空间 {free_mb} MB。",
            path=str(runtime_dir),
            free_mb=free_mb,
        )
    except OSError as error:
        return _result(
            "运行目录",
            "fail",
            f"运行目录不可写：{error}",
            path=str(runtime_dir),
        )


def _check_database(project_root: Path) -> Dict:
    database_path = _runtime_dir(project_root) / "shenzhi_sessions.db"
    if not database_path.exists():
        return _result(
            "会话数据库",
            "warn",
            "尚未创建会话数据库，首次打开网页后会自动生成。",
            path=str(database_path),
        )
    try:
        with sqlite3.connect(database_path, timeout=5) as connection:
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
            sessions = connection.execute(
                "SELECT COUNT(*) FROM chat_sessions"
            ).fetchone()[0]
        status = "pass" if integrity == "ok" else "fail"
        return _result(
            "会话数据库",
            status,
            f"SQLite quick_check={integrity}，已保存 {sessions} 个会话。",
            path=str(database_path),
            sessions=sessions,
            size_kb=round(database_path.stat().st_size / 1024, 1),
        )
    except (OSError, sqlite3.DatabaseError) as error:
        return _result(
            "会话数据库",
            "fail",
            f"数据库检查失败：{error}",
            path=str(database_path),
        )


def _check_model_config(project_root: Path) -> Dict:
    if os.getenv("SHENZHI_ENABLE_TEST_STUB") == "1":
        return _result("模型配置", "pass", "当前启用了本地测试模型桩。")
    if os.getenv("DEEPSEEK_API_KEY") or _configured_api_key(project_root):
        return _result("模型配置", "pass", "DeepSeek API Key 已配置。")
    return _result(
        "模型配置",
        "warn",
        "未检测到 DeepSeek API Key；如使用 Ollama，本项可忽略。",
    )


def _check_dependencies() -> Dict:
    dependencies = ["streamlit", "requests", "openai"]
    missing = [
        dependency
        for dependency in dependencies
        if importlib.util.find_spec(dependency) is None
    ]
    return _result(
        "Python 依赖",
        "pass" if not missing else "fail",
        "核心依赖已安装。" if not missing else f"缺少依赖：{', '.join(missing)}",
        missing=missing,
    )


def run_health_check(
    project_root: Optional[Path] = None,
    *,
    expected_case_count: int = 234,
) -> Dict:
    root = Path(project_root or BASE_DIR).resolve()
    cases_check = _check_case_library(root, expected_case_count)
    checks = [
        cases_check,
        _check_tongue_images(root, expected_case_count, cases_check),
        _check_runtime_storage(root),
        _check_database(root),
        _check_model_config(root),
        _check_dependencies(),
    ]
    summary = summarize_health(checks)
    return {
        "generated_at": _now(),
        "project_root": str(root),
        "summary": summary,
        "checks": checks,
        "system": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
    }


def summarize_health(checks: List[Dict]) -> Dict:
    counts = {
        status: sum(1 for check in checks if check["status"] == status)
        for status in ["pass", "warn", "fail"]
    }
    if counts["fail"]:
        label = "存在异常"
        status = "fail"
    elif counts["warn"]:
        label = "可运行，有提示"
        status = "warn"
    else:
        label = "状态正常"
        status = "pass"
    return {"status": status, "label": label, **counts}


def health_report_markdown(report: Dict) -> str:
    summary = report["summary"]
    lines = [
        "# 神志思训系统自检报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 项目目录：`{report['project_root']}`",
        f"- 总体状态：**{summary['label']}**",
        f"- 检查结果：通过 {summary['pass']} 项，提示 {summary['warn']} 项，异常 {summary['fail']} 项",
        "",
        "## 自检明细",
        "",
        "| 项目 | 状态 | 说明 |",
        "| --- | --- | --- |",
    ]
    status_labels = {"pass": "通过", "warn": "提示", "fail": "异常"}
    for check in report["checks"]:
        lines.append(
            f"| {check['name']} | {status_labels[check['status']]} | {check['message']} |"
        )
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 自检不会发送病例内容，也不会调用 DeepSeek API。",
            "- 诊断包不会包含病例 JSON、舌象原图、API Key 或原始问诊数据库。",
            "",
        ]
    )
    return "\n".join(lines)


def save_health_report(report: Dict, report_dir: Optional[Path] = None) -> Path:
    output_dir = Path(report_dir or REPORT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"系统自检报告_{_stamp()}.md"
    report_path.write_text(health_report_markdown(report), encoding="utf-8")
    report_path.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report_path


def _sanitized_secrets_status(project_root: Path) -> str:
    return (
        'DEEPSEEK_API_KEY = "***configured***"\n'
        if _configured_api_key(project_root)
        else 'DEEPSEEK_API_KEY = "***not configured***"\n'
    )


def create_diagnostic_bundle(
    project_root: Optional[Path] = None,
    report: Optional[Dict] = None,
) -> Path:
    root = Path(project_root or BASE_DIR).resolve()
    runtime_dir = _runtime_dir(root)
    diagnostic_dir = runtime_dir / "diagnostics"
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    report = report or run_health_check(root)
    bundle_path = diagnostic_dir / f"神志思训诊断包_{_stamp()}.zip"

    with tempfile.TemporaryDirectory(prefix="shenzhi-diagnostic-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        (temp_dir / "系统自检报告.md").write_text(
            health_report_markdown(report),
            encoding="utf-8",
        )
        (temp_dir / "系统自检报告.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (temp_dir / "secrets_status.toml").write_text(
            _sanitized_secrets_status(root),
            encoding="utf-8",
        )
        config_path = root / ".streamlit" / "config.toml"
        if config_path.exists():
            shutil.copy2(config_path, temp_dir / "streamlit_config.toml")
        log_path = runtime_dir / "shenzhi_app.log"
        if log_path.exists():
            log_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            (temp_dir / "shenzhi_app_tail.log").write_text(
                "\n".join(log_lines[-300:]) + "\n",
                encoding="utf-8",
            )
        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(temp_dir.iterdir()):
                archive.write(path, arcname=path.name)
    return bundle_path
