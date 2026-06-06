import ast
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Tuple

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"
sys.path.insert(0, str(PROJECT_ROOT))

import stability_store as store
from scale_assessments import empty_scale_assessments


def first_case_title() -> str:
    case_file = sorted((PROJECT_ROOT / "cases").glob("*.json"))[0]
    case = json.loads(case_file.read_text(encoding="utf-8"))
    return case.get("title", case.get("case_id", "未命名病例"))


def minimal_chat(**overrides) -> Dict:
    chat = {
        "title": "恢复测试会话",
        "case_title": first_case_title(),
        "model": "deepseek-v4-flash",
        "history": [],
        "supervisor_history": [],
        "score_log": [],
        "soap": "",
        "review_report": "",
        "review_report_generated_at": "",
        "training_submitted": False,
        "submitted_at": "",
        "completion_snapshot": {},
        "scale_assessments": empty_scale_assessments(),
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
    chat.update(overrides)
    return chat


class StabilityRegressionTests(unittest.TestCase):
    def setUp(self):
        self._old_cwd = Path.cwd()
        os.chdir(PROJECT_ROOT)
        self._tempdir = tempfile.TemporaryDirectory(prefix="shenzhi-regression-")
        self.runtime_dir = Path(self._tempdir.name)
        store.RUNTIME_DIR = self.runtime_dir
        store.DB_PATH = self.runtime_dir / "shenzhi_sessions.db"
        store.LOG_PATH = self.runtime_dir / "shenzhi_app.log"
        os.environ["SHENZHI_RUNTIME_DIR"] = str(self.runtime_dir)
        os.environ["SHENZHI_ENABLE_TEST_STUB"] = "1"
        os.environ["SHENZHI_MODEL_STUB"] = "success"
        os.environ["SHENZHI_MODEL_STUB_RESPONSE"] = "（测试模型回答）最近心情有些低落，睡眠也不太好。"

    def tearDown(self):
        os.chdir(self._old_cwd)
        for key in [
            "SHENZHI_RUNTIME_DIR",
            "SHENZHI_ENABLE_TEST_STUB",
            "SHENZHI_MODEL_STUB",
            "SHENZHI_MODEL_STUB_RESPONSE",
        ]:
            os.environ.pop(key, None)
        self._tempdir.cleanup()

    def run_app(self) -> AppTest:
        app = AppTest.from_file(str(APP_PATH))
        app.run(timeout=20)
        self.assertEqual([], list(app.error))
        return app

    def read_log(self) -> str:
        return store.LOG_PATH.read_text(encoding="utf-8") if store.LOG_PATH.exists() else ""

    def only_chat(self) -> Dict:
        sessions = store.load_chat_sessions()
        self.assertEqual(1, len(sessions))
        return next(iter(sessions.values()))

    @staticmethod
    def find_button(app: AppTest, *, key_contains: str = "", label: str = ""):
        for button in app.button:
            if key_contains and key_contains not in str(button.key):
                continue
            if label and button.label != label:
                continue
            return button
        raise AssertionError(f"Button not found: key_contains={key_contains!r}, label={label!r}")

    @staticmethod
    def find_text_input(app: AppTest, label: str):
        for text_input in app.text_input:
            if text_input.label == label:
                return text_input
        raise AssertionError(f"Text input not found: {label}")

    def test_initial_render_does_not_call_model_or_generate_soap(self):
        app = self.run_app()
        self.assertEqual(["督导老师", "量表评估", "评分详情", "病例资料"], [tab.label for tab in app.tabs])
        self.assertNotIn("model_stub_used", self.read_log())
        self.assertEqual("", self.only_chat()["soap"])

    def test_patient_question_success_is_saved(self):
        app = self.run_app()
        self.find_text_input(app, "学生问诊输入").set_value("你最近有什么不舒服吗？")
        self.find_button(app, key_contains="FormSubmitter:patient_form_", label="➤").click().run(timeout=20)

        chat = self.only_chat()
        self.assertEqual(1, len(chat["history"]))
        self.assertEqual("你最近有什么不舒服吗？", chat["history"][0]["doctor"])
        self.assertIn("测试模型回答", chat["history"][0]["patient"])
        self.assertEqual({}, chat["pending_patient_retry"])

    def test_patient_failure_is_not_saved_and_can_retry(self):
        os.environ["SHENZHI_MODEL_STUB"] = "failure"
        app = self.run_app()
        self.find_text_input(app, "学生问诊输入").set_value("最近睡得怎么样？")
        self.find_button(app, key_contains="FormSubmitter:patient_form_", label="➤").click().run(timeout=20)

        chat = self.only_chat()
        self.assertEqual([], chat["history"])
        self.assertEqual("最近睡得怎么样？", chat["pending_patient_retry"]["question"])
        self.find_button(app, label="重新生成患者回答")

        os.environ["SHENZHI_MODEL_STUB"] = "success"
        self.find_button(app, label="重新生成患者回答").click().run(timeout=20)
        chat = self.only_chat()
        self.assertEqual(1, len(chat["history"]))
        self.assertEqual("最近睡得怎么样？", chat["history"][0]["doctor"])
        self.assertEqual({}, chat["pending_patient_retry"])

    def test_supervisor_failure_falls_back_to_rule_hint(self):
        os.environ["SHENZHI_MODEL_STUB"] = "failure"
        app = self.run_app()
        self.find_text_input(app, "向督导老师提问").set_value("下一步优先问什么？")
        self.find_button(app, key_contains="FormSubmitter:supervisor_form_").click().run(timeout=20)

        chat = self.only_chat()
        self.assertEqual(1, len(chat["supervisor_history"]))
        feedback = chat["supervisor_history"][0]["supervisor"]
        self.assertIn("当前模型未连接", feedback)
        self.assertEqual(["督导老师", "量表评估", "评分详情", "病例资料"], [tab.label for tab in app.tabs])

    def test_generate_soap_before_submission_does_not_call_model(self):
        app = self.run_app()
        self.find_button(app, key_contains="generate_soap_").click().run(timeout=20)
        self.assertNotIn("model_stub_used", self.read_log())
        self.assertEqual("", self.only_chat()["soap"])

    def test_review_report_generates_without_submission_and_does_not_call_model(self):
        app = self.run_app()
        self.find_button(app, key_contains="generate_review_report_").click().run(timeout=20)
        chat = self.only_chat()
        self.assertIn("训练闭环 2.1 综合复盘报告", chat["review_report"])
        self.assertIn("病例库标准对照", chat["review_report"])
        self.assertNotIn("model_stub_used", self.read_log())

    def test_complete_history_generates_review_report_without_model(self):
        history = [
            {"doctor": "你最近最困扰的问题是什么，持续多久了？", "patient": "最近心情低落，差不多两个月。"},
            {"doctor": "开始前有没有明显压力或生活变化？", "patient": "考试前压力很大。"},
            {"doctor": "最近入睡、早醒、多梦和睡眠时长怎么样？", "patient": "入睡困难，也容易早醒。"},
            {"doctor": "有没有听到别人听不到的声音，或觉得有人监视、议论、伤害你？", "patient": "没有。"},
            {"doctor": "情绪最差时有没有想过不想活、轻生或伤害自己？", "patient": "没有具体想过。"},
            {"doctor": "方便描述一下舌头颜色、舌苔厚薄，或者之前中医说过脉象吗？", "patient": "舌尖有点红，苔有点白腻。"},
        ]
        store.save_all_chat_sessions(
            {
                "submitted01": minimal_chat(
                    title="完整问诊记录",
                    history=history,
                )
            },
            "submitted01",
        )

        app = self.run_app()
        self.find_button(app, key_contains="generate_review_report_").click().run(timeout=20)
        chat = self.only_chat()
        self.assertIn("训练闭环 2.1 综合复盘报告", chat["review_report"])
        self.assertIn("病例库标准对照", chat["review_report"])
        self.assertIn("量表评估复盘", chat["review_report"])
        self.assertIn("SOAP 病历状态", chat["review_report"])
        self.assertNotIn("model_stub_used", self.read_log())

    def test_hamd17_panel_starts_and_saves_complete_score(self):
        app = self.run_app()
        self.find_button(app, label="开始 HAMD-17 教学评分").click().run(timeout=20)

        hamd17_inputs = [
            selectbox
            for selectbox in app.selectbox
            if selectbox.label[:1].isdigit()
        ]
        self.assertEqual(17, len(hamd17_inputs))
        for selectbox in hamd17_inputs:
            selectbox.set_value(selectbox.options[1])
        self.find_button(app, key_contains="FormSubmitter:hamd17_form_").click().run(timeout=20)

        hamd17 = self.only_chat()["scale_assessments"]["hamd17"]
        self.assertEqual("completed", hamd17["status"])
        self.assertEqual(0, sum(hamd17["answers"].values()))

    def test_hama_panel_starts_and_saves_complete_score(self):
        app = self.run_app()
        self.find_button(app, label="开始 HAMA 教学评分").click().run(timeout=20)

        hama_inputs = [
            selectbox
            for selectbox in app.selectbox
            if selectbox.label[:1].isdigit()
        ]
        self.assertEqual(14, len(hama_inputs))
        for selectbox in hama_inputs:
            selectbox.set_value("1分：轻度")
        self.find_button(app, key_contains="FormSubmitter:hama_form_").click().run(timeout=20)

        hama = self.only_chat()["scale_assessments"]["hama"]
        self.assertEqual("completed", hama["status"])
        self.assertEqual(14, sum(hama["answers"].values()))

    def test_interrupted_request_is_recovered_as_retry(self):
        store.save_all_chat_sessions(
            {
                "restore01": minimal_chat(
                    request_state={
                        "kind": "patient",
                        "status": "running",
                        "question": "页面中断前的问题",
                        "created_at": "06-02 00:01",
                    }
                )
            },
            "restore01",
        )
        app = self.run_app()
        chat = self.only_chat()
        self.assertEqual({}, chat["request_state"])
        self.assertEqual("页面中断前的问题", chat["pending_patient_retry"]["question"])
        self.find_button(app, label="重新生成患者回答")

    def test_long_chat_restores_and_loads_earlier_turns(self):
        history = [
            {"doctor": f"第{i}个问题", "patient": f"第{i}个回答"}
            for i in range(1, 21)
        ]
        store.save_all_chat_sessions(
            {"restore20": minimal_chat(title="恢复的长问诊", history=history)},
            "restore20",
        )
        app = self.run_app()
        self.find_button(app, label="加载更早记录（还有 4 轮）").click().run(timeout=20)
        load_buttons = [button.label for button in app.button if "加载更早记录" in button.label]
        self.assertEqual([], load_buttons)

    def test_score_detail_markup_and_sticky_layout_regression(self):
        app = self.run_app()
        markdown_values = [item.value for item in app.markdown]
        score_detail_blocks = [
            value
            for value in markdown_values
            if value.startswith("<div class='dimension-score-list'>")
        ]

        self.assertEqual(1, len(score_detail_blocks))
        self.assertNotIn("\n", score_detail_blocks[0])
        self.assertNotIn("优先补强", "\n".join(markdown_values))

        source = APP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("height=555", source)
        self.assertNotIn("height=690", source)
        self.assertIn("--sz-sidebar-width: 14rem", source)
        self.assertIn("--sz-score-width: 18rem", source)
        self.assertIn("--sz-sidebar: #1a2332", source)
        self.assertIn("figma_chat_area_", source)
        self.assertIn("figma_chat_scroll_", source)
        self.assertIn("figma_composer_", source)
        self.assertIn("figma_score_panel_", source)
        self.assertNotIn("quick_case_select_", source)
        self.assertNotIn("快捷操作", source)
        self.assertIn('placeholder="输入您的回复消息..."', source)
        self.assertIn("figma-mic-button", source)
        self.assertIn("导出问诊记录", source)
        self.assertNotIn('st.form_submit_button("结束问诊"', source)
        self.assertNotIn('st.button("结束问诊 / 提交训练"', source)
        self.assertNotIn("训练提交", source)
        self.assertNotIn("训练设置", source)
        self.assertIn("figma_brand_logo_html", source)
        self.assertNotIn("[class*=\"st-key-assistant_workspace_\"]", source)
        self.assertIn('class="figma-avatar {role_class}"', source)
        self.assertIn('role_avatar = "医" if role == "doctor" else "患"', source)

    def test_sqlite_save_restore_delete(self):
        store.save_all_chat_sessions({"abc123": minimal_chat(title="数据库测试")}, "abc123")
        self.assertEqual("abc123", store.load_active_chat_id())
        self.assertEqual("数据库测试", store.load_chat_sessions()["abc123"]["title"])
        store.delete_chat_session("abc123")
        self.assertEqual({}, store.load_chat_sessions())

    def test_psychosis_question_scores_correct_dimension(self):
        source = APP_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        needed = {
            "get_case_required_questions",
            "required_question_keywords",
            "build_case_required_score_items",
            "dialogue_text_from_history",
            "keyword_matches",
            "find_question_evidence",
            "risk_denial_evidence",
            "score_dialogue",
        }
        selected = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in needed
        ]
        for node in selected:
            node.decorator_list = []
        namespace = {"Dict": Dict, "List": List, "Tuple": Tuple}
        exec(compile(ast.Module(body=selected, type_ignores=[]), "score_extract", "exec"), namespace)
        history = [
            {
                "doctor": "有没有听到别人听不到的声音，或觉得有人监视、议论、伤害你？",
                "patient": "没有。",
            }
        ]
        score, _ = namespace["score_dialogue"](history, {})
        self.assertIn("精神病性症状", score["鉴别诊断意识"]["hit"])
        self.assertEqual(5.0, score["鉴别诊断意识"]["score"])

    def test_natural_communication_skills_receive_score(self):
        source = APP_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        needed = {
            "get_case_required_questions",
            "required_question_keywords",
            "build_case_required_score_items",
            "dialogue_text_from_history",
            "keyword_matches",
            "find_question_evidence",
            "risk_denial_evidence",
            "score_dialogue",
        }
        selected = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in needed
        ]
        for node in selected:
            node.decorator_list = []
        namespace = {"Dict": Dict, "List": List, "Tuple": Tuple}
        exec(compile(ast.Module(body=selected, type_ignores=[]), "score_extract", "exec"), namespace)
        history = [
            {
                "doctor": "听起来这段时间确实不容易。如果愿意，你可以慢慢说说最近最困扰你的事情。",
                "patient": "最近总是提不起劲。",
            },
            {
                "doctor": "我总结一下：你最近心情低落，也睡不好，对吗？还有没有遗漏？",
                "patient": "差不多就是这些。",
            },
        ]
        score, _ = namespace["score_dialogue"](history, {})
        communication = score["沟通技巧"]
        self.assertGreaterEqual(communication["score"], 8.0)
        self.assertIn("共情回应", communication["hit"])
        self.assertIn("总结确认", communication["hit"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
