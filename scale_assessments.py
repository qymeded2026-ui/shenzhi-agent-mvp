"""Structured clinician-rated teaching-scale state and evidence helpers."""

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional


def score_options(*descriptions: str) -> Dict[str, Optional[int]]:
    options: Dict[str, Optional[int]] = {"未记录": None}
    for score, description in enumerate(descriptions):
        options[f"{score}分：{description}"] = score
    return options


HAMD17_ITEMS = [
    {
        "key": "depressed_mood",
        "label": "抑郁心境",
        "options": score_options("无", "仅在询问时表达", "自发口头表达", "通过表情、姿势或声音表现", "几乎仅表达这一状态"),
    },
    {
        "key": "guilt",
        "label": "有罪感",
        "options": score_options("无", "自责，觉得让人失望", "有罪感或反复思考过错", "认为当前疾病是惩罚，或有罪恶妄想", "出现谴责性幻听或幻视"),
    },
    {
        "key": "suicide",
        "label": "自杀",
        "options": score_options("无", "觉得活着没有意义", "希望自己已经死亡，或有相关想法", "有自杀观念或姿态", "有自杀企图"),
    },
    {
        "key": "insomnia_early",
        "label": "入睡困难",
        "options": score_options("无", "偶有入睡困难", "每晚均有入睡困难"),
    },
    {
        "key": "insomnia_middle",
        "label": "睡眠不深",
        "options": score_options("无", "睡眠浅或不安稳", "夜间醒来，离床活动"),
    },
    {
        "key": "insomnia_late",
        "label": "早醒",
        "options": score_options("无", "清晨提早醒来但能再次入睡", "醒后无法再次入睡"),
    },
    {
        "key": "work_activities",
        "label": "工作和兴趣",
        "options": score_options("无困难", "感到能力或兴趣下降", "兴趣、爱好或活动减少", "活动时间明显减少或效率下降", "因疾病停止工作或活动"),
    },
    {
        "key": "retardation",
        "label": "迟缓",
        "options": score_options("正常", "访谈中轻度迟缓", "访谈中明显迟缓", "访谈困难", "完全不能交流"),
    },
    {
        "key": "agitation",
        "label": "激越",
        "options": score_options("无", "坐立不安", "手部小动作明显", "来回走动，不能安坐", "反复搓手、咬甲或拉扯头发"),
    },
    {
        "key": "anxiety_psychic",
        "label": "精神性焦虑",
        "options": score_options("无", "主观紧张和易激惹", "为小事担忧", "面容或言谈显露焦虑", "明显恐惧"),
    },
    {
        "key": "anxiety_somatic",
        "label": "躯体性焦虑",
        "options": score_options("无", "轻度", "中度", "重度", "严重影响功能"),
    },
    {
        "key": "somatic_gastrointestinal",
        "label": "胃肠道躯体症状",
        "options": score_options("无", "食欲减退但无需督促进食", "进食困难，需要督促或辅助"),
    },
    {
        "key": "somatic_general",
        "label": "全身躯体症状",
        "options": score_options("无", "四肢、背部或头部沉重，或精力下降", "上述症状明显"),
    },
    {
        "key": "genital_symptoms",
        "label": "性症状",
        "options": score_options("无", "轻度", "重度"),
    },
    {
        "key": "hypochondriasis",
        "label": "疑病",
        "options": score_options("无", "关注自身躯体", "忧虑健康问题", "频繁诉说或请求帮助", "疑病妄想"),
    },
    {
        "key": "loss_weight",
        "label": "体重减轻",
        "options": score_options("无", "可能有体重减轻", "明确体重减轻"),
    },
    {
        "key": "insight",
        "label": "自知力",
        "options": score_options("认识到自己有抑郁或疾病", "承认有病但归因于其他原因", "否认患病"),
    },
]

HAMA14_ITEMS = [
    {
        "key": "anxious_mood",
        "label": "焦虑心境",
        "description": "担心、忧虑，感到最坏的事情将要发生，易激惹。",
    },
    {
        "key": "tension",
        "label": "紧张",
        "description": "紧张感、易疲劳、不能放松、易哭、易惊跳或坐立不安。",
    },
    {
        "key": "fears",
        "label": "害怕",
        "description": "害怕黑暗、陌生人、独处、动物、交通工具或人群。",
    },
    {
        "key": "insomnia",
        "label": "失眠",
        "description": "入睡困难、睡眠中断、睡眠不深、醒后疲倦、梦魇或夜惊。",
    },
    {
        "key": "intellectual",
        "label": "认知功能",
        "description": "注意力难以集中或记忆力较差。",
    },
    {
        "key": "depressed_mood",
        "label": "抑郁心境",
        "description": "兴趣减退、缺乏愉快感、忧郁、早醒或昼重夜轻。",
    },
    {
        "key": "somatic_muscular",
        "label": "肌肉系统症状",
        "description": "肌肉酸痛、僵硬、肌阵挛、磨牙或声音发抖。",
    },
    {
        "key": "somatic_sensory",
        "label": "感觉系统症状",
        "description": "耳鸣、视物模糊、冷热感、虚弱感或刺痛感。",
    },
    {
        "key": "cardiovascular",
        "label": "心血管系统症状",
        "description": "心动过速、心悸、胸痛、血管搏动感或晕厥感。",
    },
    {
        "key": "respiratory",
        "label": "呼吸系统症状",
        "description": "胸闷、窒息感、叹息或呼吸困难。",
    },
    {
        "key": "gastrointestinal",
        "label": "胃肠道症状",
        "description": "吞咽困难、腹胀腹痛、恶心呕吐、腹泻、便秘或体重减轻。",
    },
    {
        "key": "genitourinary",
        "label": "生殖泌尿系统症状",
        "description": "尿频、尿急、闭经、性欲减退或相关症状。",
    },
    {
        "key": "autonomic",
        "label": "自主神经系统症状",
        "description": "口干、潮红、苍白、出汗、头晕、紧张性头痛或竖毛。",
    },
    {
        "key": "behavior_interview",
        "label": "会谈时行为表现",
        "description": "坐立不安、手抖、皱眉、面色苍白、吞咽、叹息或呼吸加快等。",
    },
]

HAMA_SCORE_OPTIONS = score_options("无", "轻度", "中度", "重度", "极重度")

SYNDROME_SCALE_GUIDANCE = {
    "肝郁脾虚证": {
        "core": "hamd17",
        "reason": "本证型病例库中低落、兴趣减退、乏力和食欲变化较常见，先完成抑郁维度评定。",
    },
    "心脾两虚证": {
        "core": "hamd17",
        "reason": "本证型病例库中低落、兴趣减退、失眠和乏力较常见，先完成抑郁维度评定。",
    },
    "心神失养证": {
        "core": "hamd17",
        "reason": "本证型病例库中低落、失眠和兴趣减退较常见，先完成抑郁维度评定。",
    },
    "心肾阴虚证": {
        "core": "hamd17",
        "reason": "本证型病例库虽样本较少，但低落、失眠和风险线索较集中，先完成抑郁维度评定。",
    },
    "肝气郁结证": {
        "core": "hama",
        "reason": "本证型病例库中焦虑、烦躁、失眠和胸闷等线索较常见，先完成焦虑维度评定。",
    },
    "痰气郁结证": {
        "core": "hama",
        "reason": "本证型病例库中焦虑、胸闷和咽部异物感等线索较常见，先完成焦虑维度评定。",
    },
    "气郁化火证": {
        "core": "hama",
        "reason": "本证型病例库中易激惹、烦躁和失眠等线索较常见，先完成焦虑维度评定。",
    },
}

CLINICIAN_SCALE_CONFIG = {
    "hamd17": {
        "label": "HAMD-17",
        "domains": {
            "情绪低落": ["情绪低落", "心情", "难过", "沮丧", "绝望", "开心", "高兴"],
            "睡眠": ["睡眠", "睡觉", "失眠", "入睡", "早醒", "夜里", "多梦"],
            "兴趣与活动": ["兴趣", "动力", "精力", "活动", "工作", "学习", "做事", "懒得"],
            "焦虑": ["焦虑", "紧张", "担心", "害怕", "心慌", "坐立不安"],
            "食欲与躯体症状": ["食欲", "胃口", "体重", "乏力", "头痛", "胸闷", "身体"],
            "自杀风险": ["自杀", "轻生", "不想活", "伤害自己", "活着没意思", "死"],
        },
    },
    "hama": {
        "label": "HAMA",
        "reference_key": "HAMA",
        "domains": {
            "焦虑情绪": ["焦虑", "担心", "不安", "烦躁", "紧张", "顾虑"],
            "紧张与恐惧": ["害怕", "恐惧", "惊恐", "放松", "坐立不安", "发抖"],
            "睡眠": ["睡眠", "睡觉", "失眠", "入睡", "早醒", "多梦"],
            "认知与注意": ["注意力", "集中", "记忆", "脑子", "思考"],
            "躯体感觉": ["疼痛", "酸痛", "僵硬", "乏力", "耳鸣", "头晕", "身体"],
            "心血管与呼吸": ["心慌", "心悸", "胸闷", "呼吸", "憋气", "气短"],
            "胃肠与泌尿": ["食欲", "胃口", "恶心", "腹胀", "腹泻", "便秘", "尿频"],
        },
    },
}


def empty_scale_assessments() -> Dict[str, Dict[str, Any]]:
    return {
        "hamd17": {
            "status": "not_started",
            "answers": {},
            "completed_at": "",
        },
        "hama": {
            "status": "not_started",
            "answers": {},
            "completed_at": "",
        },
    }


def normalize_scale_assessments(value: Any) -> Dict[str, Dict[str, Any]]:
    normalized = empty_scale_assessments()
    if not isinstance(value, dict):
        return normalized

    for scale_key, defaults in normalized.items():
        incoming = value.get(scale_key)
        if not isinstance(incoming, dict):
            continue
        for key in defaults:
            if key in incoming:
                normalized[scale_key][key] = deepcopy(incoming[key])

    answers = normalized["hamd17"].get("answers")
    normalized["hamd17"]["answers"] = answers if isinstance(answers, dict) else {}
    answers = normalized["hama"].get("answers")
    normalized["hama"]["answers"] = answers if isinstance(answers, dict) else {}
    return normalized


def timestamp_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def hamd17_progress(answers: Dict[str, Any]) -> int:
    return sum(
        1
        for item in HAMD17_ITEMS
        if answers.get(item["key"]) in set(item["options"].values()) - {None}
    )


def hamd17_total(answers: Dict[str, Any]) -> Optional[int]:
    if hamd17_progress(answers) != len(HAMD17_ITEMS):
        return None
    return sum(int(answers[item["key"]]) for item in HAMD17_ITEMS)


def hamd17_partial_total(answers: Dict[str, Any]) -> int:
    return sum(
        int(answers[item["key"]])
        for item in HAMD17_ITEMS
        if answers.get(item["key"]) in set(item["options"].values()) - {None}
    )


def hama_progress(answers: Dict[str, Any]) -> int:
    valid_scores = {0, 1, 2, 3, 4}
    return sum(1 for item in HAMA14_ITEMS if answers.get(item["key"]) in valid_scores)


def hama_total(answers: Dict[str, Any]) -> Optional[int]:
    if hama_progress(answers) != len(HAMA14_ITEMS):
        return None
    return sum(int(answers[item["key"]]) for item in HAMA14_ITEMS)


def hama_partial_total(answers: Dict[str, Any]) -> int:
    valid_scores = {0, 1, 2, 3, 4}
    return sum(
        int(answers[item["key"]])
        for item in HAMA14_ITEMS
        if answers.get(item["key"]) in valid_scores
    )


def doctor_text(history: List[Dict[str, Any]]) -> str:
    return " ".join(
        str(turn.get("doctor", ""))
        for turn in history
        if isinstance(turn, dict) and turn.get("doctor")
    )


def clinician_scale_evidence(history: List[Dict[str, Any]], scale_key: str) -> Dict[str, Any]:
    config = CLINICIAN_SCALE_CONFIG.get(scale_key, {})
    domains = config.get("domains", {})
    interview_text = doctor_text(history)
    covered = []
    missing = []
    for domain, keywords in domains.items():
        if any(keyword in interview_text for keyword in keywords):
            covered.append(domain)
        else:
            missing.append(domain)
    return {
        "covered": covered,
        "missing": missing,
        "covered_count": len(covered),
        "total_count": len(domains),
    }


def scale_reference_scores(case: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(case, dict):
        return {}
    scores = case.get("scale_scores")
    return scores if isinstance(scores, dict) else {}


def recommended_scale_plan(case: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    if not isinstance(case, dict):
        case = {}
    syndrome = case.get("tcm_info", {}).get("syndrome", "未填写")
    guidance = SYNDROME_SCALE_GUIDANCE.get(
        syndrome,
        {
            "core": "hamd17",
            "reason": "当前证型尚未配置专属规则，先完成抑郁维度评定，并根据病例线索补充焦虑评定。",
        },
    )
    plan = [
        {
            "key": guidance["core"],
            "priority": "核心量表",
            "reason": guidance["reason"],
        }
    ]

    symptoms = set(case.get("main_symptoms", []))
    scores = scale_reference_scores(case)
    risk_level = str(case.get("risk_level", ""))
    depression_signals = {"心境低落", "兴趣减退", "悲观消极", "自伤", "乏力", "早醒"}
    anxiety_signals = {"焦虑", "烦躁不安", "易激惹", "心悸", "胸部满闷", "坐立不安", "失眠"}
    add_hamd17 = (
        len(symptoms & depression_signals) >= 2
        or scores.get("HAMD-24", 0) >= 24
        or "自伤自杀" in risk_level
    )
    add_hama = len(symptoms & anxiety_signals) >= 2 or scores.get("HAMA", 0) >= 20
    companion_key = "hama" if guidance["core"] == "hamd17" else "hamd17"
    companion_needed = add_hama if companion_key == "hama" else add_hamd17
    if companion_needed:
        reason = (
            "当前病例同时存在较明显的焦虑、烦躁、失眠或躯体焦虑线索，建议补充焦虑维度评定。"
            if companion_key == "hama"
            else "当前病例同时存在较明显的低落、兴趣减退、乏力或风险线索，建议补充抑郁维度评定。"
        )
        plan.append({"key": companion_key, "priority": "补充量表", "reason": reason})
    return plan


def build_scale_summary(
    scale_assessments: Any,
    case: Optional[Dict[str, Any]],
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    assessments = normalize_scale_assessments(scale_assessments)
    reference_scores = scale_reference_scores(case)
    hamd_answers = assessments["hamd17"]["answers"]
    hamd_total = hamd17_total(hamd_answers)
    hama = assessments["hama"]
    hama_answers = hama.get("answers", {})
    hama_score = hama_total(hama_answers)
    hama_reference = reference_scores.get("HAMA")

    return {
        "recommendations": recommended_scale_plan(case),
        "hamd17": {
            "status": "completed" if hamd_total is not None else assessments["hamd17"]["status"],
            "progress": hamd17_progress(hamd_answers),
            "total_items": len(HAMD17_ITEMS),
            "partial_total": hamd17_partial_total(hamd_answers),
            "total": hamd_total,
            "suicide_score": hamd_answers.get("suicide"),
            "evidence": clinician_scale_evidence(history, "hamd17"),
            "legacy_hamd24_reference": reference_scores.get("HAMD-24"),
        },
        "hama": {
            "status": "completed" if hama_score is not None else hama.get("status", "not_started"),
            "progress": hama_progress(hama_answers),
            "total_items": len(HAMA14_ITEMS),
            "partial_total": hama_partial_total(hama_answers),
            "total": hama_score,
            "reference_score": hama_reference,
            "difference": hama_score - hama_reference
            if isinstance(hama_score, (int, float)) and isinstance(hama_reference, (int, float))
            else None,
            "evidence": clinician_scale_evidence(history, "hama"),
        },
    }


def scale_summary_markdown(
    scale_assessments: Any,
    case: Optional[Dict[str, Any]],
    history: List[Dict[str, Any]],
) -> str:
    summary = build_scale_summary(scale_assessments, case, history)
    actual_lines = []
    hamd = summary["hamd17"]
    if hamd["total"] is not None:
        actual_lines.append(f"- HAMD-17：本轮逐项教学评分 {hamd['total']} 分。")
    elif hamd["progress"]:
        actual_lines.append(
            f"- HAMD-17：已记录 {hamd['progress']}/{hamd['total_items']} 项，尚未完成总分。"
        )

    hama = summary["hama"]
    if hama["total"] is not None:
        actual_lines.append(f"- HAMA：本轮逐项教学评分 {hama['total']} 分。")
    elif hama["progress"]:
        actual_lines.append(
            f"- HAMA：已记录 {hama['progress']}/{hama['total_items']} 项，尚未完成总分。"
        )

    if not actual_lines:
        actual_lines.append("- 本轮问诊尚未完成结构化量表评定。")

    reference_lines = []
    hamd24_reference = hamd.get("legacy_hamd24_reference")
    if hamd24_reference not in (None, ""):
        reference_lines.append(
            f"- HAMD-24：病例库历史参考分 {hamd24_reference} 分。版本不同，不与本轮 HAMD-17 直接比较。"
        )
    if hama.get("reference_score") not in (None, ""):
        reference_lines.append(f"- HAMA：病例库参考分 {hama['reference_score']} 分。")
    if not reference_lines:
        reference_lines.append("- 当前病例库未提供可展示的量表参考分。")

    recommendation_lines = [
        f"- {item['priority']}：{CLINICIAN_SCALE_CONFIG[item['key']]['label']}。{item['reason']}"
        for item in summary["recommendations"]
    ]

    return "\n".join(
        [
            "### 本轮实际评定",
            *actual_lines,
            "",
            "### 当前病例教学推荐",
            *recommendation_lines,
            "",
            "### 病例库教学参考",
            *reference_lines,
            "",
            "病例库参考分仅用于教学对照，不代表本轮已经完成量表评定。",
        ]
    )
