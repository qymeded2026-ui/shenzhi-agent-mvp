import unittest

from scale_assessments import (
    HAMD17_ITEMS,
    HAMA14_ITEMS,
    build_scale_summary,
    clinician_scale_evidence,
    empty_scale_assessments,
    hama_total,
    hamd17_progress,
    hamd17_total,
    normalize_scale_assessments,
    recommended_scale_plan,
    scale_summary_markdown,
)


class ScaleAssessmentTests(unittest.TestCase):
    def test_hamd17_requires_all_items_before_total(self):
        answers = {item["key"]: 1 for item in HAMD17_ITEMS[:-1]}
        self.assertEqual(16, hamd17_progress(answers))
        self.assertIsNone(hamd17_total(answers))

        answers[HAMD17_ITEMS[-1]["key"]] = 2
        self.assertEqual(18, hamd17_total(answers))

    def test_scale_summary_separates_hamd17_and_legacy_hamd24_reference(self):
        assessments = empty_scale_assessments()
        assessments["hamd17"]["answers"] = {item["key"]: 1 for item in HAMD17_ITEMS}
        case = {"scale_scores": {"HAMD-24": 23, "HAMA": 12}}

        summary = build_scale_summary(assessments, case, [])
        markdown = scale_summary_markdown(assessments, case, [])

        self.assertEqual(17, summary["hamd17"]["total"])
        self.assertEqual(23, summary["hamd17"]["legacy_hamd24_reference"])
        self.assertIn("HAMD-17：本轮逐项教学评分 17 分", markdown)
        self.assertIn("HAMD-24：病例库历史参考分 23 分", markdown)
        self.assertIn("版本不同，不与本轮 HAMD-17 直接比较", markdown)

    def test_hamd17_maximum_total_is_52(self):
        answers = {
            item["key"]: max(score for score in item["options"].values() if score is not None)
            for item in HAMD17_ITEMS
        }
        self.assertEqual(52, hamd17_total(answers))

    def test_hama_fourteen_items_maximum_total_is_56(self):
        answers = {item["key"]: 4 for item in HAMA14_ITEMS}
        self.assertEqual(14, len(HAMA14_ITEMS))
        self.assertEqual(56, hama_total(answers))

    def test_syndrome_guidance_selects_different_core_scales(self):
        depression_plan = recommended_scale_plan({"tcm_info": {"syndrome": "心脾两虚证"}})
        anxiety_plan = recommended_scale_plan({"tcm_info": {"syndrome": "肝气郁结证"}})
        self.assertEqual("hamd17", depression_plan[0]["key"])
        self.assertEqual("hama", anxiety_plan[0]["key"])

    def test_case_signals_add_companion_scale(self):
        plan = recommended_scale_plan(
            {
                "tcm_info": {"syndrome": "心神失养证"},
                "main_symptoms": ["焦虑", "心悸", "失眠"],
                "scale_scores": {"HAMA": 22},
            }
        )
        self.assertEqual(["hamd17", "hama"], [item["key"] for item in plan])

    def test_legacy_phq9_and_hamd24_session_state_is_removed(self):
        normalized = normalize_scale_assessments(
            {
                "phq9": {"status": "completed", "answers": {"mood": 3}},
                "hamd24": {"status": "completed", "total": 34},
            }
        )
        self.assertNotIn("phq9", normalized)
        self.assertNotIn("hamd24", normalized)
        self.assertEqual("not_started", normalized["hamd17"]["status"])

    def test_hama_evidence_detects_interview_domains(self):
        history = [
            {"doctor": "最近是否经常紧张担心，晚上入睡怎么样？", "patient": "有一些。"},
            {"doctor": "会不会心慌、胸闷或者觉得气短？", "patient": "偶尔会。"},
        ]
        evidence = clinician_scale_evidence(history, "hama")
        self.assertIn("焦虑情绪", evidence["covered"])
        self.assertIn("睡眠", evidence["covered"])
        self.assertIn("心血管与呼吸", evidence["covered"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
