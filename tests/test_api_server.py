import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import api_server
import stability_store as store
from scale_assessments import HAMD17_ITEMS
from shenzhi_chat_core import build_patient_messages, patient_reactivity_state, score_dialogue


class ApiServerTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory(prefix="shenzhi-api-")
        self.root = Path(self._tempdir.name)
        self.runtime_dir = self.root / "runtime"
        self.old_cwd = Path.cwd()
        self.old_runtime_env = os.environ.get("SHENZHI_RUNTIME_DIR")
        self.old_stub_env = {
            key: os.environ.get(key)
            for key in [
                "SHENZHI_ENABLE_TEST_STUB",
                "SHENZHI_MODEL_STUB",
                "SHENZHI_MODEL_STUB_RESPONSE",
            ]
        }
        self.old_runtime_dir = store.RUNTIME_DIR
        self.old_db_path = store.DB_PATH
        self.old_log_path = store.LOG_PATH

        os.environ["SHENZHI_RUNTIME_DIR"] = str(self.runtime_dir)
        os.environ["SHENZHI_ENABLE_TEST_STUB"] = "1"
        os.environ["SHENZHI_MODEL_STUB"] = "success"
        os.environ["SHENZHI_MODEL_STUB_RESPONSE"] = "（测试患者回答）最近睡眠不好，也有些心烦。"
        store.RUNTIME_DIR = self.runtime_dir
        store.DB_PATH = self.runtime_dir / "shenzhi_sessions.db"
        store.LOG_PATH = self.runtime_dir / "shenzhi_app.log"

        (self.root / "cases").mkdir()
        (self.root / "tongue_images").mkdir()
        (self.root / "tongue_images" / "case_001.jpg").write_bytes(b"fake-jpeg")
        case = {
            "case_id": "case_001",
            "title": "病例001：心脾两虚证",
            "chief_complaint": "失眠、心烦",
            "risk_level": "低风险",
            "tcm_info": {
                "syndrome": "心脾两虚证",
                "tongue": "舌淡红，苔薄白",
                "pulse": "脉细",
                "constitution": "气虚质",
                "tongue_images": ["tongue_images/case_001.jpg"],
            },
            "teaching_info": {
                "required_questions": ["主诉/病程/诱因", "睡眠/食欲/二便", "舌象脉象"],
            },
        }
        (self.root / "cases" / "case_001.json").write_text(
            json.dumps(case, ensure_ascii=False),
            encoding="utf-8",
        )
        second_case = {
            "case_id": "case_002",
            "title": "病例002：肝气郁结证",
            "chief_complaint": "胸闷、烦躁",
            "risk_level": "低风险",
            "tcm_info": {
                "syndrome": "肝气郁结证",
                "tongue": "舌红，苔薄黄",
                "pulse": "脉弦",
            },
            "teaching_info": {
                "required_questions": ["主诉/病程/诱因"],
            },
        }
        (self.root / "cases" / "case_002.json").write_text(
            json.dumps(second_case, ensure_ascii=False),
            encoding="utf-8",
        )
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.old_cwd)
        if self.old_runtime_env is None:
            os.environ.pop("SHENZHI_RUNTIME_DIR", None)
        else:
            os.environ["SHENZHI_RUNTIME_DIR"] = self.old_runtime_env
        for key, value in self.old_stub_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        store.RUNTIME_DIR = self.old_runtime_dir
        store.DB_PATH = self.old_db_path
        store.LOG_PATH = self.old_log_path
        self._tempdir.cleanup()

    def test_list_chats_bootstraps_default_session(self):
        response = api_server.list_chats()

        self.assertEqual(1, len(response["chats"]))
        self.assertEqual(response["activeChatId"], response["chats"][0]["id"])
        self.assertEqual("新问诊", response["chats"][0]["title"])
        self.assertEqual("病例001：心脾两虚证", response["chats"][0]["caseTitle"])

    def test_create_patch_and_delete_chat_flow(self):
        api_server.list_chats()

        created = api_server.create_chat()
        chat_id = created["activeChatId"]
        self.assertEqual(2, len(created["chats"]))

        renamed = api_server.patch_chat(
            chat_id,
            {"title": "随访复盘", "pinned": True, "active": True},
        )
        active = next(chat for chat in renamed["chats"] if chat["id"] == chat_id)
        self.assertEqual("随访复盘", active["title"])
        self.assertTrue(active["pinned"])
        self.assertEqual(chat_id, renamed["activeChatId"])

        exported = api_server.export_chat(chat_id)
        self.assertEqual("随访复盘", exported["session"]["title"])

        deleted = api_server.delete_chat(chat_id)
        self.assertNotIn(chat_id, {chat["id"] for chat in deleted["chats"]})
        self.assertGreaterEqual(len(deleted["chats"]), 1)
        self.assertIn(deleted["activeChatId"], {chat["id"] for chat in deleted["chats"]})

    def test_chat_detail_and_message_submission(self):
        listed = api_server.list_chats()
        chat_id = listed["activeChatId"]

        initial_detail = api_server.get_chat_detail(chat_id)
        self.assertEqual([], initial_detail["messages"])
        self.assertEqual("病例001", initial_detail["case"]["caseCode"])
        self.assertIn("supervisor", initial_detail)
        self.assertIn("scale", initial_detail)
        self.assertIn("casePanel", initial_detail)

        submitted = api_server.submit_chat_message(
            chat_id,
            {"question": "你最近睡眠怎么样？"},
        )

        self.assertEqual(2, len(submitted["messages"]))
        self.assertEqual("doctor", submitted["messages"][0]["role"])
        self.assertEqual("patient", submitted["messages"][1]["role"])
        self.assertIn("测试患者回答", submitted["messages"][1]["content"])
        self.assertIn("score", submitted["messages"][1])
        self.assertEqual({}, submitted["pendingPatientRetry"])

        exported = api_server.export_chat(chat_id)
        self.assertEqual("你最近睡眠怎么样？", exported["session"]["history"][0]["doctor"])

        pdf_export = api_server.export_chat_pdf(chat_id)
        self.assertIsNotNone(pdf_export)
        pdf_data, filename = pdf_export
        self.assertTrue(filename.endswith(".pdf"))
        self.assertTrue(pdf_data.startswith(b"%PDF-"))
        self.assertIn(b"/Type /Page", pdf_data)

    def test_tongue_question_exposes_image_in_chat_message(self):
        listed = api_server.list_chats()
        chat_id = listed["activeChatId"]

        detail = api_server.submit_chat_message(
            chat_id,
            {"question": "请你描述一下舌象和舌苔情况。"},
        )

        patient_message = detail["messages"][1]
        self.assertEqual("patient", patient_message["role"])
        self.assertEqual("case_001.jpg", patient_message["tongueImages"][0]["filename"])
        self.assertEqual("/api/tongue-images/case_001.jpg", patient_message["tongueImages"][0]["url"])

    def test_supervisor_submission_is_saved_in_chat_detail(self):
        listed = api_server.list_chats()
        chat_id = listed["activeChatId"]
        api_server.submit_chat_message(chat_id, {"question": "你最近睡眠怎么样？"})

        detail = api_server.submit_chat_supervisor(
            chat_id,
            {"question": "我下一步应该问什么？"},
        )

        self.assertEqual(1, len(detail["supervisor"]["history"]))
        feedback = detail["supervisor"]["history"][0]
        self.assertEqual("我下一步应该问什么？", feedback["question"])
        self.assertTrue(feedback["answer"])
        self.assertTrue(detail["supervisor"]["nextStepHint"])

        exported = api_server.export_chat(chat_id)
        self.assertEqual(1, len(exported["session"]["supervisor_history"]))

    def test_score_panel_payload_uses_real_case_and_score_data(self):
        listed = api_server.list_chats()
        chat_id = listed["activeChatId"]
        api_server.submit_chat_message(chat_id, {"question": "你最近睡眠怎么样？"})

        detail = api_server.get_chat_detail(chat_id)

        self.assertGreater(detail["score"]["total"], 0)
        self.assertIn("问诊完整性", detail["score"]["dimensions"])
        self.assertIn("recommendations", detail["scale"])
        self.assertGreaterEqual(len(detail["scale"]["recommendations"]), 1)
        self.assertIn("requiredQuestions", detail["casePanel"])
        self.assertIn("scoreSummary", detail["review"])

    def test_scale_submission_updates_items_and_invalidates_outputs(self):
        listed = api_server.list_chats()
        chat_id = listed["activeChatId"]
        api_server.generate_chat_review_report(chat_id)
        answers = {
            HAMD17_ITEMS[0]["key"]: 1,
            HAMD17_ITEMS[1]["key"]: 2,
        }

        detail = api_server.patch_chat_scale(
            chat_id,
            {"scaleKey": "hamd17", "answers": answers},
        )

        hamd = next(item for item in detail["scale"]["recommendations"] if item["key"] == "hamd17")
        self.assertEqual("in_progress", hamd["status"])
        self.assertEqual(2, hamd["progress"])
        self.assertEqual(1, hamd["items"][0]["value"])
        self.assertEqual("", detail["review"]["report"])

    def test_case_panel_exposes_safe_tongue_image_url(self):
        detail = api_server.get_chat_detail(api_server.list_chats()["activeChatId"])

        images = detail["casePanel"]["tongueImages"]
        self.assertEqual("case_001.jpg", images[0]["filename"])
        self.assertEqual("/api/tongue-images/case_001.jpg", images[0]["url"])
        expected_image = (self.root / "tongue_images" / "case_001.jpg").resolve()
        self.assertEqual(
            expected_image,
            api_server.resolve_tongue_image("case_001.jpg").resolve(),
        )
        self.assertEqual(
            expected_image,
            api_server.resolve_tongue_image("../case_001.jpg").resolve(),
        )

    def test_workbench_options_and_chat_settings(self):
        listed = api_server.list_chats()
        chat_id = listed["activeChatId"]

        options = api_server.list_workbench_options()
        self.assertGreaterEqual(len(options["cases"]), 2)
        self.assertIn("deepseek-chat", {item["value"] for item in options["models"]})

        created = api_server.create_chat(
            {"caseTitle": "病例002：肝气郁结证", "model": "deepseek-chat"}
        )
        created_detail = api_server.get_chat_detail(created["activeChatId"])
        self.assertEqual("病例002", created_detail["case"]["caseCode"])
        self.assertEqual("deepseek-chat", created_detail["model"])

        switched = api_server.patch_chat_settings(
            chat_id,
            {"caseTitle": "病例002：肝气郁结证", "model": "deepseek-chat"},
        )
        self.assertEqual("病例002", switched["case"]["caseCode"])
        self.assertEqual("deepseek-chat", switched["model"])

        api_server.submit_chat_message(chat_id, {"question": "你最近有什么不舒服吗？"})
        blocked = api_server.patch_chat_settings(
            chat_id,
            {"caseTitle": "病例001：心脾两虚证"},
        )
        self.assertIn("已有问诊记录", blocked["error"])
        self.assertEqual("病例002", blocked["case"]["caseCode"])

    def test_review_report_and_soap_actions_return_detail(self):
        listed = api_server.list_chats()
        chat_id = listed["activeChatId"]
        api_server.submit_chat_message(chat_id, {"question": "你最近睡眠怎么样？"})

        report_detail = api_server.generate_chat_review_report(chat_id)
        self.assertIn("综合复盘报告", report_detail["review"]["report"])
        self.assertTrue(report_detail["review"]["reportGeneratedAt"])

        soap_detail = api_server.generate_chat_soap(chat_id)
        self.assertIn("暂不能生成 SOAP", soap_detail["error"])
        exported = api_server.export_chat(chat_id)
        self.assertEqual("", exported["session"]["soap"])

    def test_failed_message_submission_keeps_history_clean(self):
        listed = api_server.list_chats()
        chat_id = listed["activeChatId"]
        os.environ["SHENZHI_MODEL_STUB"] = "failure"

        submitted = api_server.submit_chat_message(
            chat_id,
            {"question": "最近有什么不舒服吗？"},
        )

        self.assertIn("error", submitted)
        self.assertEqual([], submitted["messages"])
        self.assertEqual("最近有什么不舒服吗？", submitted["pendingPatientRetry"]["question"])

        exported = api_server.export_chat(chat_id)
        self.assertEqual([], exported["session"]["history"])

    def test_patient_reactivity_guides_sensitive_mechanical_questions(self):
        listed = api_server.list_chats()
        chat_id = listed["activeChatId"]

        api_server.submit_chat_message(
            chat_id,
            {"question": "有没有自杀？有没有具体计划？"},
        )

        exported = api_server.export_chat(chat_id)
        reactivity = exported["session"]["history"][0]["patient_reactivity"]
        self.assertEqual("防御和回避", reactivity["stance"])
        self.assertIn("自杀", reactivity["sensitive_topics"])
        self.assertGreaterEqual(reactivity["current_mechanical_score"], 2)

    def test_patient_reactivity_softens_after_empathy(self):
        case = api_server.load_cases()[0]
        history = [
            {"doctor": "有没有自杀？有没有具体计划？", "patient": "我不想说这个。"},
            {"doctor": "有没有幻听？有没有妄想？", "patient": "你一直问这些干嘛？"},
        ]
        question = "这个问题可能有点敏感，不想说也没关系。情绪最差时有没有想过伤害自己？"

        reactivity = patient_reactivity_state(case, history, question)
        messages = build_patient_messages(case, history, question, reactivity=reactivity)

        self.assertTrue(reactivity["supportive_question"])
        self.assertEqual("迟疑但愿意一点点说", reactivity["stance"])
        self.assertIn("伤害自己", reactivity["sensitive_topics"])
        self.assertIn("本轮患者反应状态", messages[0]["content"])
        self.assertIn("不要仍然完整、耐心、条理清晰地回答", messages[0]["content"])

    def test_refusal_without_effective_answer_does_not_score_content(self):
        history = [
            {
                "doctor": "有没有听到别人听不到的声音，或觉得有人监视、议论、伤害你？",
                "patient": "（低头沉默了几秒）……没什么特别感觉。不想说这个。",
            }
        ]

        score, _detail = score_dialogue(history, {})

        differential = score["鉴别诊断意识"]
        self.assertNotIn("精神病性症状", differential["hit"])
        self.assertEqual(0, differential["score"])

    def test_partial_risk_answer_only_scores_answered_items(self):
        history = [
            {
                "doctor": "有没有自杀？有没有具体计划？有没有伤害自己？",
                "patient": "（低头，声音很轻）……有想过吧。……但没有计划。……能不说这个吗。",
            }
        ]

        score, _detail = score_dialogue(history, {})

        risk = score["风险筛查"]
        self.assertIn("自杀意念", risk["hit"])
        self.assertIn("具体计划", risk["hit"])
        self.assertNotIn("自伤/冲动", risk["hit"])
        self.assertEqual(10.0, risk["score"])

    def test_followup_disclosure_scores_after_patient_answers(self):
        history = [
            {
                "doctor": "有没有自杀？有没有具体计划？有没有伤害自己？",
                "patient": "（低头，声音很轻）……有想过吧。……但没有计划。……能不说这个吗。",
            },
            {
                "doctor": "我知道这个很难说，可以慢慢来。之前有没有真的伤害过自己？",
                "patient": "有一次用小刀划过胳膊，但我不太想细说。",
            },
        ]

        score, _detail = score_dialogue(history, {})

        risk = score["风险筛查"]
        self.assertIn("自伤/冲动", risk["hit"])
        self.assertEqual(15.0, risk["score"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
