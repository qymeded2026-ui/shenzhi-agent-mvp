import argparse
import json
import os
import statistics
import sys
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"
sys.path.insert(0, str(PROJECT_ROOT))

import stability_store as store


def case_titles() -> List[str]:
    titles = []
    for case_file in sorted((PROJECT_ROOT / "cases").glob("*.json")):
        case = json.loads(case_file.read_text(encoding="utf-8"))
        titles.append(case.get("title", case.get("case_id", "未命名病例")))
    if not titles:
        raise RuntimeError("未找到 cases/*.json，无法执行压力测试。")
    return titles


def chat_payload(
    *,
    title: str,
    case_title: str,
    turns: int = 0,
    updated_at: str = "06-02 00:00",
) -> Dict:
    return {
        "title": title,
        "case_title": case_title,
        "model": "deepseek-v4-flash",
        "history": [
            {
                "doctor": f"第{i}轮压力测试问题：最近症状有什么变化？",
                "patient": f"第{i}轮压力测试回答：最近有一些不舒服。",
            }
            for i in range(1, turns + 1)
        ],
        "supervisor_history": [],
        "score_log": [],
        "soap": "",
        "training_submitted": False,
        "submitted_at": "",
        "completion_snapshot": {},
        "show_supervisor_history": False,
        "open_supervisor_history_once": False,
        "supervisor_history_revision": 0,
        "supervisor_feedback_page": 0,
        "case_widget_revision": 0,
        "pending_patient_retry": {},
        "request_state": {},
        "created_at": "06-02 00:00",
        "updated_at": updated_at,
    }


def configure_runtime(runtime_dir: Path) -> None:
    store.RUNTIME_DIR = runtime_dir
    store.DB_PATH = runtime_dir / "shenzhi_sessions.db"
    store.LOG_PATH = runtime_dir / "shenzhi_app.log"
    os.environ["SHENZHI_RUNTIME_DIR"] = str(runtime_dir)
    os.environ["SHENZHI_ENABLE_TEST_STUB"] = "1"
    os.environ["SHENZHI_MODEL_STUB"] = "success"
    os.environ["SHENZHI_MODEL_STUB_RESPONSE"] = (
        "（压力测试模型回答）最近心情有些低落，睡眠也不太好。"
    )


def find_text_input(app: AppTest, label: str):
    for text_input in app.text_input:
        if text_input.label == label:
            return text_input
    raise AssertionError(f"未找到输入框：{label}")


def find_button(app: AppTest, *, key_contains: str = "", label: str = ""):
    for button in app.button:
        if key_contains and key_contains not in str(button.key):
            continue
        if label and button.label != label:
            continue
        return button
    raise AssertionError(f"未找到按钮：key={key_contains!r}, label={label!r}")


class AcceptanceRunner:
    def __init__(self, report_dir: Path):
        self.report_dir = report_dir
        self.results = []
        self.titles = case_titles()

    def run(self, name: str, description: str, callback) -> None:
        started_at = time.perf_counter()
        try:
            metrics = callback()
            passed = True
            details = "通过"
        except Exception as error:
            metrics = {}
            passed = False
            details = f"{type(error).__name__}: {error}"
            traceback.print_exc()
        duration_ms = round((time.perf_counter() - started_at) * 1000, 1)
        self.results.append(
            {
                "name": name,
                "description": description,
                "passed": passed,
                "duration_ms": duration_ms,
                "metrics": metrics,
                "details": details,
            }
        )
        marker = "PASS" if passed else "FAIL"
        print(f"[{marker}] {name}: {duration_ms} ms")
        if metrics:
            print(f"       {json.dumps(metrics, ensure_ascii=False)}")
        if not passed:
            print(f"       {details}")

    def sqlite_bulk_restore(self) -> Dict:
        sessions = {
            f"bulk-{index:03d}": chat_payload(
                title=f"批量会话 {index:03d}",
                case_title=self.titles[index % len(self.titles)],
                turns=30,
                updated_at=f"06-02 00:{index % 60:02d}",
            )
            for index in range(150)
        }
        started_at = time.perf_counter()
        changed_rows = store.save_all_chat_sessions(sessions, "bulk-149")
        save_ms = round((time.perf_counter() - started_at) * 1000, 1)

        started_at = time.perf_counter()
        restored = store.load_chat_sessions(limit=200)
        load_ms = round((time.perf_counter() - started_at) * 1000, 1)

        started_at = time.perf_counter()
        noop_changes = store.save_all_chat_sessions(sessions, "bulk-149")
        noop_save_ms = round((time.perf_counter() - started_at) * 1000, 1)

        assert len(restored) == 150, f"应恢复 150 个会话，实际 {len(restored)}"
        assert changed_rows >= 151, f"首次写入变更行数异常：{changed_rows}"
        assert noop_changes == 0, f"未修改数据不应重复写入，实际 {noop_changes}"
        assert save_ms < 4000, f"批量保存过慢：{save_ms} ms"
        assert load_ms < 2000, f"批量恢复过慢：{load_ms} ms"
        return {
            "sessions": 150,
            "turns_per_session": 30,
            "save_ms": save_ms,
            "load_ms": load_ms,
            "noop_save_ms": noop_save_ms,
            "db_kb": round(store.DB_PATH.stat().st_size / 1024, 1),
        }

    def sqlite_concurrent_writes(self) -> Dict:
        workers = 10
        writes_per_worker = 60

        def write_worker(worker_id: int) -> List[float]:
            latencies = []
            for iteration in range(writes_per_worker):
                chat = chat_payload(
                    title=f"并发写入 {worker_id}-{iteration}",
                    case_title=self.titles[(worker_id + iteration) % len(self.titles)],
                    turns=iteration % 8,
                    updated_at=f"06-02 01:{iteration % 60:02d}",
                )
                started_at = time.perf_counter()
                store.save_chat_session(f"concurrent-{worker_id:02d}", chat)
                latencies.append((time.perf_counter() - started_at) * 1000)
            return latencies

        started_at = time.perf_counter()
        all_latencies = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(write_worker, worker_id) for worker_id in range(workers)]
            for future in as_completed(futures):
                all_latencies.extend(future.result())
        total_ms = round((time.perf_counter() - started_at) * 1000, 1)

        restored = store.load_chat_sessions(limit=500)
        p95_ms = round(statistics.quantiles(all_latencies, n=20)[18], 1)
        assert all(f"concurrent-{worker_id:02d}" in restored for worker_id in range(workers))
        assert total_ms < 8000, f"并发写入耗时过长：{total_ms} ms"
        assert p95_ms < 250, f"并发单次写入 P95 过高：{p95_ms} ms"
        return {
            "workers": workers,
            "total_writes": workers * writes_per_worker,
            "total_ms": total_ms,
            "write_p95_ms": p95_ms,
            "write_max_ms": round(max(all_latencies), 1),
        }

    def rapid_case_switches(self) -> Dict:
        chat_id = "case-switch"
        chat = chat_payload(title="病例切换压力测试", case_title=self.titles[0])
        store.save_chat_session(chat_id, chat)

        started_at = time.perf_counter()
        for index in range(180):
            chat["case_title"] = self.titles[index % len(self.titles)]
            chat["case_widget_revision"] = index + 1
            chat["history"] = []
            chat["updated_at"] = f"06-02 02:{index % 60:02d}"
            store.save_chat_session(chat_id, chat)
        total_ms = round((time.perf_counter() - started_at) * 1000, 1)

        restored = store.load_chat_sessions(limit=500)[chat_id]
        assert restored["case_title"] == chat["case_title"]
        assert restored["case_widget_revision"] == 180
        assert total_ms < 4000, f"病例切换持久化耗时过长：{total_ms} ms"
        return {
            "switches": 180,
            "total_ms": total_ms,
            "average_ms": round(total_ms / 180, 2),
            "final_case": restored["case_title"],
        }

    def long_chat_render(self) -> Dict:
        store.save_all_chat_sessions(
            {
                "render-30": chat_payload(
                    title="30轮长问诊渲染",
                    case_title=self.titles[0],
                    turns=30,
                )
            },
            "render-30",
        )
        started_at = time.perf_counter()
        app = AppTest.from_file(str(APP_PATH))
        app.run(timeout=20)
        render_ms = round((time.perf_counter() - started_at) * 1000, 1)
        assert [] == list(app.error), list(app.error)
        find_button(app, label="加载更早记录（还有 14 轮）").click().run(timeout=20)
        assert not [
            button.label for button in app.button if "加载更早记录" in button.label
        ]
        assert render_ms < 8000, f"30轮问诊初次渲染过慢：{render_ms} ms"
        return {
            "turns": 30,
            "initial_render_ms": render_ms,
            "pagination": "16 + 14",
        }

    def many_sidebar_sessions_render(self) -> Dict:
        sessions = {
            f"sidebar-{index:03d}": chat_payload(
                title=f"侧栏会话 {index:03d}",
                case_title=self.titles[index % len(self.titles)],
                turns=index % 4,
                updated_at=f"06-02 03:{index % 60:02d}",
            )
            for index in range(50)
        }
        store.save_all_chat_sessions(sessions, "sidebar-049")
        started_at = time.perf_counter()
        app = AppTest.from_file(str(APP_PATH))
        app.run(timeout=20)
        render_ms = round((time.perf_counter() - started_at) * 1000, 1)
        assert [] == list(app.error), list(app.error)
        assert any(button.label == "● 侧栏会话 049" for button in app.button)
        assert render_ms < 8000, f"50个近期会话渲染过慢：{render_ms} ms"
        return {
            "sidebar_sessions": 50,
            "initial_render_ms": render_ms,
            "sidebar_container": "固定高度滚动区",
        }

    def patient_roundtrip_burst(self) -> Dict:
        store.save_all_chat_sessions(
            {"patient-burst": chat_payload(title="连续问诊压力测试", case_title=self.titles[0])},
            "patient-burst",
        )
        app = AppTest.from_file(str(APP_PATH))
        app.run(timeout=20)
        assert [] == list(app.error), list(app.error)

        roundtrip_ms = []
        for index in range(1, 21):
            find_text_input(app, "学生问诊输入").set_value(f"第{index}轮：最近还有哪些不舒服？")
            started_at = time.perf_counter()
            find_button(app, key_contains="FormSubmitter:patient_form_", label="➤").click().run(timeout=20)
            roundtrip_ms.append((time.perf_counter() - started_at) * 1000)
            assert [] == list(app.error), list(app.error)

        restored = store.load_chat_sessions(limit=500)["patient-burst"]
        p95_ms = round(statistics.quantiles(roundtrip_ms, n=20)[18], 1)
        assert len(restored["history"]) == 20, f"连续问诊仅保存 {len(restored['history'])} 轮"
        assert p95_ms < 3000, f"连续问诊页面重跑 P95 过高：{p95_ms} ms"
        return {
            "roundtrips": 20,
            "roundtrip_average_ms": round(statistics.mean(roundtrip_ms), 1),
            "roundtrip_p95_ms": p95_ms,
            "roundtrip_max_ms": round(max(roundtrip_ms), 1),
        }

    def model_failure_recovery(self) -> Dict:
        store.save_all_chat_sessions(
            {"failure-recovery": chat_payload(title="失败恢复压力测试", case_title=self.titles[0])},
            "failure-recovery",
        )
        app = AppTest.from_file(str(APP_PATH))
        app.run(timeout=20)
        assert [] == list(app.error), list(app.error)

        os.environ["SHENZHI_MODEL_STUB"] = "failure"
        find_text_input(app, "学生问诊输入").set_value("网络中断时的问题")
        find_button(app, key_contains="FormSubmitter:patient_form_", label="➤").click().run(timeout=20)
        failed_chat = store.load_chat_sessions(limit=500)["failure-recovery"]
        assert failed_chat["history"] == []
        assert failed_chat["pending_patient_retry"]["question"] == "网络中断时的问题"

        os.environ["SHENZHI_MODEL_STUB"] = "success"
        find_button(app, label="重新生成患者回答").click().run(timeout=20)
        recovered_chat = store.load_chat_sessions(limit=500)["failure-recovery"]
        assert len(recovered_chat["history"]) == 1
        assert recovered_chat["pending_patient_retry"] == {}
        return {
            "failure_saved_as_retry": True,
            "retry_restored_turns": len(recovered_chat["history"]),
        }

    def write_report(self) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        passed_count = sum(1 for result in self.results if result["passed"])
        total_count = len(self.results)
        overall = "通过" if passed_count == total_count else "未通过"

        json_path = self.report_dir / f"稳定性验收1.3报告_{filename_stamp}.json"
        markdown_path = self.report_dir / f"稳定性验收1.3报告_{filename_stamp}.md"
        json_path.write_text(
            json.dumps(
                {
                    "generated_at": generated_at,
                    "overall": overall,
                    "passed": passed_count,
                    "total": total_count,
                    "results": self.results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        lines = [
            "# 稳定性验收 1.3：真实压力测试报告",
            "",
            f"- 生成时间：{generated_at}",
            f"- 自动验收结论：**{overall}**",
            f"- 自动场景：{passed_count}/{total_count} 通过",
            "- 测试模式：本地临时 SQLite 数据库 + 本地测试模型桩，不调用 DeepSeek API，不修改真实问诊会话。",
            "",
            "## 自动压力测试结果",
            "",
            "| 场景 | 结果 | 耗时 | 关键指标 |",
            "| --- | --- | ---: | --- |",
        ]
        for result in self.results:
            metrics = "；".join(
                f"{key}={value}" for key, value in result["metrics"].items()
            )
            lines.append(
                f"| {result['name']} | {'通过' if result['passed'] else '失败'} | "
                f"{result['duration_ms']} ms | {metrics or result['details']} |"
            )

        lines.extend(
            [
                "",
                "## 覆盖范围",
                "",
                "- 150 个问诊会话、每个 30 轮的批量保存、恢复与无变化写入跳过。",
                "- 10 个并发线程共 600 次 SQLite 会话写入。",
                "- 180 次快速病例切换持久化。",
                "- 30 轮长问诊页面渲染与“加载更早记录”分页。",
                "- 50 个近期问诊会话的侧栏恢复与渲染。",
                "- 20 轮连续患者问诊提交、测试模型回答与落盘。",
                "- 模型中断后保留待重试问题，并在恢复后重新生成患者回答。",
                "",
                "## 浏览器人工验收清单",
                "",
                "自动测试通过后，仍建议在演示电脑上完成以下检查：",
                "",
                "- [ ] 连续问诊 30 轮，确认页面自然向下延展、输入栏保持贴底，并可加载更早记录。",
                "- [ ] 连续切换 20 个病例，确认页面不会卡死或丢失当前病例。",
                "- [ ] 问诊中途刷新浏览器，确认近期问诊和当前会话可恢复。",
                "- [ ] 暂时断开网络后提交一次问题，再恢复网络并点击“重新生成患者回答”。",
                "- [ ] 连续向督导老师提问 10 次，确认历史反馈可翻页。",
                "- [ ] 同时打开两个浏览器标签页，确认不会导致数据库损坏。",
                "",
                "## 说明",
                "",
                "本报告用于本机 MVP 稳定性验收。它验证了高频操作下的页面与本地存储行为，"
                "但不等同于正式服务器环境中的多人并发压测。上线教学前仍需在部署服务器上补充网络层与多人并发测试。",
                "",
            ]
        )
        markdown_path.write_text("\n".join(lines), encoding="utf-8")
        return markdown_path

    def execute(self) -> Path:
        scenarios = [
            (
                "批量会话保存与恢复",
                "150 个会话，每个 30 轮，验证保存、恢复与无变化跳过写入。",
                self.sqlite_bulk_restore,
            ),
            (
                "SQLite 并发写入",
                "10 个并发线程共 600 次写入，验证本地持久化可靠性。",
                self.sqlite_concurrent_writes,
            ),
            (
                "快速病例切换",
                "模拟 180 次病例切换并校验最终病例状态。",
                self.rapid_case_switches,
            ),
            (
                "30轮长问诊渲染",
                "验证聊天区初次渲染与更早记录分页加载。",
                self.long_chat_render,
            ),
            (
                "50个近期会话渲染",
                "验证近期问诊侧栏在较多会话下的恢复与渲染。",
                self.many_sidebar_sessions_render,
            ),
            (
                "20轮连续患者问诊",
                "使用本地测试模型连续提交问题，验证页面重跑和持久化。",
                self.patient_roundtrip_burst,
            ),
            (
                "模型中断与恢复",
                "模拟模型失败，验证问题不会丢失且可重新生成回答。",
                self.model_failure_recovery,
            ),
        ]
        old_cwd = Path.cwd()
        try:
            os.chdir(PROJECT_ROOT)
            for name, description, callback in scenarios:
                with tempfile.TemporaryDirectory(prefix="shenzhi-stress-") as temporary_dir:
                    configure_runtime(Path(temporary_dir))
                    self.run(name, description, callback)
        finally:
            os.chdir(old_cwd)
        return self.write_report()


def main() -> int:
    parser = argparse.ArgumentParser(description="神志思训稳定性验收 1.3")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=PROJECT_ROOT / "reports",
        help="验收报告输出目录",
    )
    args = parser.parse_args()
    runner = AcceptanceRunner(args.report_dir)
    report_path = runner.execute()
    passed_count = sum(1 for result in runner.results if result["passed"])
    total_count = len(runner.results)
    print()
    print(f"自动压力测试：{passed_count}/{total_count} 场景通过")
    print(f"验收报告：{report_path}")
    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
