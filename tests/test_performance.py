import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.sys.path.insert(0, str(PROJECT_ROOT))

import stability_store as store


def first_case_title() -> str:
    case_file = sorted((PROJECT_ROOT / "cases").glob("*.json"))[0]
    case = json.loads(case_file.read_text(encoding="utf-8"))
    return case.get("title", case.get("case_id", "未命名病例"))


def chat_with_turns(turn_count: int):
    return {
        "title": f"{turn_count}轮性能测试",
        "case_title": first_case_title(),
        "model": "deepseek-v4-flash",
        "history": [
            {"doctor": f"第{i}个问题", "patient": f"第{i}个回答"}
            for i in range(1, turn_count + 1)
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
        "updated_at": "06-02 00:00",
    }


class PerformanceRegressionTests(unittest.TestCase):
    def setUp(self):
        self._old_cwd = Path.cwd()
        os.chdir(PROJECT_ROOT)
        self._tempdir = tempfile.TemporaryDirectory(prefix="shenzhi-performance-")
        self.runtime_dir = Path(self._tempdir.name)
        store.RUNTIME_DIR = self.runtime_dir
        store.DB_PATH = self.runtime_dir / "shenzhi_sessions.db"
        store.LOG_PATH = self.runtime_dir / "shenzhi_app.log"
        os.environ["SHENZHI_RUNTIME_DIR"] = str(self.runtime_dir)
        os.environ["SHENZHI_ENABLE_TEST_STUB"] = "1"
        os.environ["SHENZHI_MODEL_STUB"] = "success"

    def tearDown(self):
        os.chdir(self._old_cwd)
        for key in [
            "SHENZHI_RUNTIME_DIR",
            "SHENZHI_ENABLE_TEST_STUB",
            "SHENZHI_MODEL_STUB",
        ]:
            os.environ.pop(key, None)
        self._tempdir.cleanup()

    def test_noop_database_save_skips_updates(self):
        sessions = {"performance01": chat_with_turns(4)}
        first_changes = store.save_all_chat_sessions(sessions, "performance01")
        noop_changes = store.save_all_chat_sessions(sessions, "performance01")
        sessions["performance01"]["title"] = "发生变化"
        changed_again = store.save_all_chat_sessions(sessions, "performance01")

        self.assertGreaterEqual(first_changes, 2)
        self.assertEqual(0, noop_changes)
        self.assertEqual(1, changed_again)

    def test_thirty_turn_chat_initial_render_is_paginated(self):
        store.save_all_chat_sessions(
            {"performance30": chat_with_turns(30)},
            "performance30",
        )
        started_at = time.perf_counter()
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py"))
        app.run(timeout=20)
        elapsed = time.perf_counter() - started_at

        self.assertEqual([], list(app.error))
        self.assertIn(
            "加载更早记录（还有 14 轮）",
            [button.label for button in app.button],
        )
        self.assertLess(elapsed, 8.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
