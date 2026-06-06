import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import requests
from openai import OpenAI

from scale_assessments import (
    CLINICIAN_SCALE_CONFIG,
    HAMA14_ITEMS,
    HAMA_SCORE_OPTIONS,
    HAMD17_ITEMS,
    build_scale_summary,
    hama_total,
    hamd17_total,
    normalize_scale_assessments,
    timestamp_now,
)
import stability_store as store


DEFAULT_MODEL = "deepseek-v4-flash"
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_REQUEST_TIMEOUT = 25
MODEL_MAX_ATTEMPTS = 3


class ModelCallError(RuntimeError):
    """Raised when the patient model cannot produce a safe persisted answer."""


def now_label() -> str:
    return datetime.now().strftime("%m-%d %H:%M")


def get_case_syndrome(case: Dict) -> str:
    return case.get("tcm_info", {}).get("syndrome", "未填写")


def get_case_diagnosis(case: Dict) -> str:
    return case.get("western_diagnosis", {}).get("category", "未填写")


def get_case_required_questions(case: Dict) -> List[str]:
    questions = case.get("teaching_info", {}).get("required_questions", [])
    return questions if isinstance(questions, list) else []


def required_question_keywords(item: str) -> List[str]:
    keyword_map = {
        "主诉/病程/诱因": [
            "哪里不舒服",
            "主要",
            "不舒服",
            "症状",
            "困扰",
            "多久",
            "多长时间",
            "什么时候",
            "诱因",
            "原因",
            "压力",
            "发生什么",
            "刺激",
        ],
        "睡眠/食欲/二便": [
            "睡眠",
            "失眠",
            "入睡",
            "早醒",
            "多梦",
            "食欲",
            "胃口",
            "大便",
            "小便",
            "二便",
            "饮食",
        ],
        "自伤自杀风险": [
            "自杀",
            "轻生",
            "不想活",
            "活着没意思",
            "伤害自己",
            "伤害过自己",
            "自伤",
            "自残",
            "结束生命",
            "割腕",
            "划过",
            "划伤",
            "跳楼",
            "吃药",
            "死亡",
            "具体计划",
            "保护因素",
        ],
        "幻听妄想": [
            "幻听",
            "幻觉",
            "妄想",
            "听到声音",
            "别人听不到的声音",
            "听到别人听不到",
            "看见别人看不到",
            "有人害",
            "有人要害",
            "有人想害",
            "有人监视",
            "有人议论",
            "有人伤害你",
            "被害",
            "被监视",
            "被议论",
            "被控制",
            "别人议论",
            "有人跟踪",
            "怀疑别人",
        ],
        "躁狂或轻躁狂": [
            "躁狂",
            "轻躁狂",
            "兴奋",
            "话多",
            "精力",
            "精力旺盛",
            "睡得少也不困",
            "睡得少",
            "不用睡",
            "花钱",
            "冲动消费",
            "特别自信",
            "想法很多",
            "脑子转得快",
            "活动增多",
            "易怒",
        ],
        "舌象脉象": ["舌", "舌象", "舌苔", "舌质", "脉", "脉象"],
        "既往史/用药史/家族史": [
            "既往",
            "以前",
            "用药",
            "药物",
            "吃药",
            "家族",
            "家人",
            "遗传",
            "病史",
        ],
    }
    if item in keyword_map:
        return keyword_map[item]

    keywords = []
    for part in item.replace("；", "/").replace("、", "/").split("/"):
        part = part.strip()
        if part:
            keywords.append(part)
    return keywords or [item]


def build_case_required_score_items(case: Dict) -> Dict[str, List[str]]:
    return {item: required_question_keywords(item) for item in get_case_required_questions(case)}


def prepare_case_for_prompt(case: Dict) -> Dict:
    case_for_prompt = json.loads(json.dumps(case, ensure_ascii=False))
    case_for_prompt.pop("_file", None)

    tcm_info = case_for_prompt.get("tcm_info", {})
    tcm_info.pop("tongue_images", None)
    tcm_info.pop("tongue_image_status", None)
    return case_for_prompt


def read_deepseek_key_from_secrets() -> str:
    secrets_path = Path(".streamlit") / "secrets.toml"
    if not secrets_path.exists():
        return ""

    for raw_line in secrets_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not line.startswith("DEEPSEEK_API_KEY"):
            continue
        _key, _separator, value = line.partition("=")
        return value.strip().strip('"').strip("'")
    return ""


def get_deepseek_api_key() -> str:
    return os.getenv("DEEPSEEK_API_KEY", "").strip() or read_deepseek_key_from_secrets()


def call_patient_model(messages: List[Dict], model: str, temperature: float = 0.4) -> str:
    model_stub = (
        os.getenv("SHENZHI_MODEL_STUB", "").strip().lower()
        if os.getenv("SHENZHI_ENABLE_TEST_STUB") == "1"
        else ""
    )
    if model_stub:
        store.log_event("model_stub_used", mode=model_stub, model=model)
        if model_stub == "success":
            return os.getenv(
                "SHENZHI_MODEL_STUB_RESPONSE",
                "（测试患者回答）最近心情有些低落，睡眠也不太好。",
            )
        if model_stub == "failure":
            raise ModelCallError("测试环境模拟模型暂时不可用。")
        raise ModelCallError(f"未知的测试模型模式：{model_stub}")

    api_key = get_deepseek_api_key()
    provider = "deepseek" if api_key else "ollama"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }

    last_error = ""
    for attempt in range(1, MODEL_MAX_ATTEMPTS + 1):
        started_at = time.monotonic()
        try:
            if api_key:
                response = OpenAI(
                    api_key=api_key,
                    base_url="https://api.deepseek.com",
                    timeout=MODEL_REQUEST_TIMEOUT,
                    max_retries=0,
                ).chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                )
                answer = response.choices[0].message.content.strip()
            else:
                response = requests.post(
                    OLLAMA_URL,
                    json=payload,
                    timeout=(3.05, MODEL_REQUEST_TIMEOUT),
                )
                response.raise_for_status()
                answer = response.json()["message"]["content"].strip()

            store.log_event(
                "model_request_succeeded",
                provider=provider,
                model=model,
                attempt=attempt,
                elapsed_ms=round((time.monotonic() - started_at) * 1000),
            )
            return answer
        except Exception as error:
            last_error = str(error)
            store.log_event(
                "model_request_failed",
                provider=provider,
                model=model,
                attempt=attempt,
                elapsed_ms=round((time.monotonic() - started_at) * 1000),
                error=last_error,
            )
            if attempt < MODEL_MAX_ATTEMPTS:
                time.sleep(0.8 * (2 ** (attempt - 1)))

    if api_key:
        raise ModelCallError("模型服务暂时不可用，已自动重试，请稍后重新生成。")
    raise ModelCallError("本地模型暂未连接，已自动重试，请确认 Ollama 已启动后重新生成。")


EMPATHY_KEYWORDS = [
    "听起来",
    "我能理解",
    "我理解",
    "确实不容易",
    "挺不容易",
    "很难熬",
    "辛苦",
    "难受",
    "委屈",
    "害怕",
    "慢慢说",
    "别着急",
    "不用急",
    "我在听",
    "没关系",
    "不会评判",
    "不勉强",
]

PERMISSION_OR_EXPLANATION_KEYWORDS = [
    "如果你愿意",
    "方便说",
    "愿意说",
    "可以慢慢",
    "为了了解",
    "为了帮",
    "我想确认",
    "我需要确认",
    "这个问题可能有点敏感",
    "你可以只说愿意说的部分",
    "不想说也没关系",
]

CLOSED_OR_CHECKLIST_KEYWORDS = [
    "有没有",
    "是否",
    "有无",
    "是不是",
    "吗",
    "否认",
    "具体计划",
    "药物",
    "家族史",
    "既往史",
    "幻听",
    "妄想",
    "自杀",
    "轻生",
]

SENSITIVE_TOPIC_KEYWORDS = [
    "自杀",
    "轻生",
    "不想活",
    "活着没意思",
    "伤害自己",
    "自伤",
    "自残",
    "割腕",
    "跳楼",
    "吞药",
    "创伤",
    "阴影",
    "受刺激",
    "被欺负",
    "霸凌",
    "家暴",
    "打你",
    "性侵",
    "侵犯",
    "骚扰",
    "分手",
    "离婚",
    "去世",
    "死亡",
    "家庭",
    "父母",
    "亲人",
    "伴侣",
    "恋爱",
    "学校",
    "同学",
    "工作压力",
    "为什么会这样",
    "发生什么事",
    "诱因",
]


def text_has_any(text: str, keywords: List[str]) -> bool:
    return any(keyword in text for keyword in keywords if keyword)


def question_mechanical_score(question: str) -> int:
    question = str(question or "")
    score = 0
    if text_has_any(question, CLOSED_OR_CHECKLIST_KEYWORDS):
        score += 1
    if question.count("？") + question.count("?") >= 2 or question.count("、") >= 2:
        score += 1
    if len(question) <= 18 and not text_has_any(question, EMPATHY_KEYWORDS):
        score += 1
    if text_has_any(question, ["接着问", "下一个", "还有没有", "直接回答", "配合一下"]):
        score += 1
    return score


def is_supportive_question(question: str) -> bool:
    return text_has_any(question, EMPATHY_KEYWORDS) or text_has_any(question, PERMISSION_OR_EXPLANATION_KEYWORDS)


def patient_sensitive_topics(case: Dict, question: str) -> List[str]:
    question = str(question or "")
    topics = [keyword for keyword in SENSITIVE_TOPIC_KEYWORDS if keyword in question]
    behavior_rules = case.get("behavior_rules", {}) if isinstance(case, dict) else {}
    for trigger in behavior_rules.get("emotion_triggers", []) or []:
        if trigger and trigger in question:
            topics.append(str(trigger))
    return list(dict.fromkeys(topics))[:8]


def recent_mechanical_pressure(history: List[Dict]) -> int:
    pressure = 0
    for item in history[-3:]:
        question = str(item.get("doctor", ""))
        if question_mechanical_score(question) >= 2 and not is_supportive_question(question):
            pressure += 1
    return pressure


def patient_reactivity_state(case: Dict, history: List[Dict], question: str) -> Dict:
    question = str(question or "")
    supportive = is_supportive_question(question)
    sensitive_topics = patient_sensitive_topics(case, question)
    current_mechanical_score = question_mechanical_score(question)
    recent_pressure = recent_mechanical_pressure(history)
    risk_level = str(case.get("risk_level", ""))
    age = case.get("basic_info", {}).get("age")
    is_minor = isinstance(age, int) and age < 18
    high_risk_case = any(keyword in risk_level for keyword in ["高", "危", "自伤", "自杀"])

    stance = "谨慎配合"
    intensity = "低"
    disclosure_rule = "回答医生问到的部分，保持简短口语化。"
    visible_behaviors = ["回答简短", "语气贴近病例情绪"]

    if supportive and sensitive_topics:
        stance = "迟疑但愿意一点点说"
        intensity = "中"
        disclosure_rule = "先表达迟疑或难以启齿，再透露一个小线索，不要一次性完整交代。"
        visible_behaviors = ["停顿", "小心试探", "只说一部分"]
    elif sensitive_topics and (recent_pressure > 0 or current_mechanical_score >= 2):
        stance = "防御和回避"
        intensity = "高" if high_risk_case or is_minor else "中"
        disclosure_rule = "不要耐心完整作答；可以回避、反问为什么要问、要求先别追，最多透露很少信息。"
        visible_behaviors = ["回避眼神", "短句", "反问", "不愿继续展开"]
    elif sensitive_topics:
        stance = "明显防御"
        intensity = "中"
        disclosure_rule = "先表达不想谈或不确定能否说，再给出含糊回答；等待医生共情或解释目的后再放松。"
        visible_behaviors = ["犹豫", "含糊", "转移话题"]
    elif recent_pressure >= 2 and not supportive:
        stance = "烦躁不配合"
        intensity = "中"
        disclosure_rule = "不要像问卷一样逐项配合；可以说“你一直这样问我有点烦”，只回答一小部分。"
        visible_behaviors = ["皱眉", "不耐烦", "回答变短"]
    elif current_mechanical_score >= 2 and not supportive:
        stance = "轻度不耐烦"
        intensity = "低到中"
        disclosure_rule = "回答可以带一点迟疑或抵触，不需要把所有细节都讲清楚。"
        visible_behaviors = ["迟疑", "简短", "略带抵触"]
    elif supportive and recent_pressure > 0:
        stance = "关系有所缓和"
        intensity = "低到中"
        disclosure_rule = "可以承认刚才有点紧张或不想说，现在愿意补充一小段。"
        visible_behaviors = ["语气缓和", "开始补充一点细节"]

    return {
        "stance": stance,
        "intensity": intensity,
        "supportive_question": supportive,
        "current_mechanical_score": current_mechanical_score,
        "recent_mechanical_pressure": recent_pressure,
        "sensitive_topics": sensitive_topics,
        "minor_patient": is_minor,
        "high_risk_case": high_risk_case,
        "visible_behaviors": visible_behaviors,
        "disclosure_rule": disclosure_rule,
    }


def build_patient_messages(
    case: Dict,
    history: List[Dict],
    question: str,
    reactivity: Optional[Dict] = None,
) -> List[Dict]:
    history_text = "\n".join(
        [f"医生：{h['doctor']}\n患者：{h['patient']}" for h in history[-8:]]
    )
    reactivity = reactivity or patient_reactivity_state(case, history, question)
    system_prompt = f"""
你正在扮演一名中医精神心理方向的模拟患者，用于医学生问诊训练。
你必须严格依据以下病例角色卡回答，不能编造病例卡以外的关键医学信息。

【病例角色卡】
{json.dumps(prepare_case_for_prompt(case), ensure_ascii=False, indent=2)}

【扮演规则】
1. 你是患者，不是医生，不能主动说出诊断、证型、方药名称。
2. 不要一次性说出所有症状。医生问到什么，你再逐步透露。
3. 回答要口语化、真实、简短，一般控制在80字以内。
4. 如果医生没有问自杀风险、舌象、脉象、既往史等，不要主动全部交代。
5. 你不是耐心配合问卷的机器人。医生连续机械追问、没有解释目的、没有共情，或突然触及创伤/自伤/家庭/羞耻议题时，可以不配合、回避、反问、沉默、烦躁，只回答一小部分。
6. 如果医生先共情、解释为什么问、允许你慢慢说或不勉强，你可以从防御逐步变得愿意表达，但仍不能一次性全交代。
7. 触及核心心理创伤、自伤自杀、家庭冲突、被欺负、亲密关系等敏感内容时，先表现迟疑、害怕、羞耻或防御；除非医生共情并建立安全感，否则不要完整展开。
8. 可以使用少量真实患者反应，如“我不太想说这个”“你问这个干嘛”“能不能别一直问这个”“我有点烦了”“……算了”，但不能脱离病例角色。
9. 不要把不配合演成攻击医生；保持教学安全边界，不辱骂、不威胁、不提供真实处置建议。
10. 不要使用“肝郁脾虚证、心脾两虚证、辨证、证型”等专业术语。
11. 如果医生问到舌象，你只能用患者口吻描述舌头颜色、舌苔厚薄等，不要说图片路径。
12. 严禁回答中出现 tongue_images、case_001.jpg、case_002.jpg、图片路径、文件名等内容。

【本轮患者反应状态】
{json.dumps(reactivity, ensure_ascii=False, indent=2)}

【本轮表演要求】
请优先遵守“本轮患者反应状态”里的 stance、visible_behaviors 和 disclosure_rule。
如果状态为防御、回避、烦躁或不配合，本轮不要仍然完整、耐心、条理清晰地回答医生的所有问题。
如果状态为关系缓和或迟疑但愿意说，本轮可先表达情绪，再透露一个有限细节。
"""
    user_prompt = f"""
【既往对话】
{history_text if history_text else '暂无'}

【医生本轮提问】
{question}

请以患者身份自然回答。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def asks_tongue(question: str) -> bool:
    keywords = ["舌", "舌象", "舌苔", "舌质"]
    return any(keyword in question for keyword in keywords)


def get_tongue_images(case: Dict) -> List[str]:
    images = case.get("tcm_info", {}).get("tongue_images", [])
    valid_images = []
    for image in images:
        if isinstance(image, str) and os.path.exists(image):
            valid_images.append(image)
    if valid_images:
        return valid_images

    case_id = case.get("case_id", "")
    if not case_id:
        return []

    for extension in [".jpg", ".jpeg", ".png", ".webp", ".JPG", ".JPEG", ".PNG"]:
        candidate = os.path.join("tongue_images", f"{case_id}{extension}")
        if os.path.exists(candidate):
            return [candidate]
    return []


def keyword_matches(text: str, keywords: List[str]) -> List[str]:
    text = str(text or "")
    return [keyword for keyword in keywords if keyword and keyword in text]


ANSWER_REFUSAL_KEYWORDS = [
    "不想说",
    "不愿意说",
    "不想回答",
    "不愿回答",
    "不想谈",
    "别问",
    "不要问",
    "能不说",
    "能不能不说",
    "先别问",
    "不想继续",
    "我不想讲",
    "我不想聊",
    "问这个干嘛",
]

VAGUE_NONANSWER_KEYWORDS = [
    "没什么特别",
    "没什么感觉",
    "不知道",
    "不清楚",
    "说不清",
    "记不清",
    "想不起来",
    "还好",
    "一般",
    "差不多",
]

GENERIC_DENIAL_KEYWORDS = [
    "没有",
    "没想过",
    "没听到",
    "没觉得",
    "不觉得",
    "不会",
    "不是",
    "没发生",
    "没出现",
]

GENERIC_AFFIRMATION_KEYWORDS = [
    "有",
    "有过",
    "想过",
    "会",
    "确实",
    "经常",
    "总是",
    "偶尔",
    "听到",
    "看到",
    "觉得",
    "睡不着",
    "睡不好",
    "早醒",
    "胃口",
    "便秘",
    "口干",
    "口苦",
    "心慌",
    "胸闷",
    "头痛",
    "难受",
]


def clean_patient_answer(answer: str) -> str:
    text = str(answer or "")
    for left, right in [("（", "）"), ("(", ")")]:
        while left in text and right in text and text.index(left) < text.index(right):
            start = text.index(left)
            end = text.index(right, start)
            text = text[:start] + text[end + 1 :]
    return text.strip(" \n\t。？！?!，,；;、…")


def has_refusal(answer: str) -> bool:
    return text_has_any(answer, ANSWER_REFUSAL_KEYWORDS)


def has_vague_nonanswer(answer: str) -> bool:
    cleaned = clean_patient_answer(answer)
    return len(cleaned) <= 12 and text_has_any(cleaned, VAGUE_NONANSWER_KEYWORDS)


def has_generic_denial(answer: str) -> bool:
    return text_has_any(answer, GENERIC_DENIAL_KEYWORDS)


def has_generic_affirmation(answer: str) -> bool:
    return text_has_any(answer, GENERIC_AFFIRMATION_KEYWORDS)


def answer_matches_risk_item(answer: str, item: str) -> bool:
    answer = str(answer or "")
    if item == "自杀意念":
        positive = [
            "想过死",
            "想死",
            "不想活",
            "活着没意思",
            "轻生",
            "自杀",
            "结束生命",
            "有想过",
            "想过吧",
            "有过这种想法",
            "消极念头",
            "极端想法",
        ]
        negative = [
            "没有自杀",
            "没想过自杀",
            "没有轻生",
            "没想过轻生",
            "没有不想活",
            "没有想过死",
            "没有想死",
            "不想死",
            "没有这种想法",
        ]
        return text_has_any(answer, positive + negative)
    if item == "自伤/冲动":
        positive = [
            "伤害自己",
            "自伤",
            "自残",
            "割腕",
            "割过",
            "划过",
            "撞墙",
            "跳楼",
            "吞药",
            "吃很多药",
            "控制不住",
            "冲动",
            "摔东西",
        ]
        negative = [
            "没有伤害自己",
            "没想过伤害自己",
            "没有自伤",
            "没有自残",
            "没自伤",
            "没自残",
            "没有冲动",
            "没冲动",
            "没有做过",
            "没做过",
        ]
        return text_has_any(answer, positive + negative)
    if item == "具体计划":
        positive = [
            "具体计划",
            "计划过",
            "准备",
            "方法",
            "想好怎么",
            "刀",
            "绳",
            "跳楼",
            "吞药",
            "吃药",
            "时间",
            "地点",
        ]
        negative = [
            "没有具体计划",
            "没具体计划",
            "没有计划",
            "没计划",
            "没有准备",
            "没准备",
            "不会去做",
            "不会真的做",
            "没有方法",
            "没想好怎么做",
        ]
        return text_has_any(answer, positive + negative)
    if item == "保护因素":
        return text_has_any(
            answer,
            [
                "家人",
                "父母",
                "朋友",
                "老师",
                "同学",
                "孩子",
                "舍不得",
                "撑住",
                "求助",
                "联系",
                "陪",
                "支持",
                "牵挂",
            ],
        )
    return False


def answer_matches_differential_item(answer: str, item: str) -> bool:
    answer = str(answer or "")
    if item == "精神病性症状":
        return text_has_any(
            answer,
            [
                "没有幻听",
                "没听到",
                "没有听到",
                "没有声音",
                "没有人监视",
                "没人监视",
                "没有人议论",
                "没人议论",
                "没有人害",
                "没人害",
                "不觉得有人",
                "听到声音",
                "有人监视",
                "有人议论",
                "有人害",
                "有人跟踪",
                "被监视",
                "被议论",
                "被害",
            ],
        )
    if item == "躁狂/轻躁狂":
        return text_has_any(
            answer,
            [
                "没有过",
                "没出现",
                "不会这样",
                "睡得少也不困",
                "精力特别旺",
                "话多",
                "花钱",
                "冲动消费",
                "特别自信",
                "脑子转得快",
                "停不下来",
            ],
        )
    if item == "躯体疾病":
        return has_generic_denial(answer) or text_has_any(
            answer,
            ["甲状腺", "甲亢", "贫血", "检查", "体检", "身体病", "内科", "激素"],
        )
    if item == "药物/物质因素":
        return has_generic_denial(answer) or text_has_any(
            answer,
            ["吃药", "药", "饮酒", "喝酒", "咖啡", "毒品", "成瘾", "安眠药", "抗抑郁"],
        )
    return False


def answer_supports_score(answer: str, item: str = "", dimension: str = "", keywords: Optional[List[str]] = None) -> bool:
    cleaned = clean_patient_answer(answer)
    if not cleaned:
        return False

    keywords = keywords or []
    if dimension == "沟通技巧" or dimension == "初步总结":
        return True
    if dimension == "风险筛查":
        return answer_matches_risk_item(cleaned, item)
    if dimension == "鉴别诊断意识":
        return answer_matches_differential_item(cleaned, item)

    has_item_signal = (
        text_has_any(cleaned, keywords)
        or has_generic_denial(cleaned)
        or has_generic_affirmation(cleaned)
    )
    if has_refusal(cleaned):
        return has_item_signal
    if has_vague_nonanswer(cleaned):
        return False
    return has_item_signal or len(cleaned) >= 8


def find_question_evidence(
    history: List[Dict],
    keywords: List[str],
    item: str = "",
    dimension: str = "",
) -> Dict:
    for index, record in enumerate(history, start=1):
        question = str(record.get("doctor", ""))
        answer = str(record.get("patient", ""))
        matches = keyword_matches(question, keywords)
        if matches and answer_supports_score(answer, item=item, dimension=dimension, keywords=keywords):
            return {
                "turn": index,
                "question": question,
                "patient_answer": answer,
                "matched": matches[:4],
                "source": "doctor_question_and_patient_answer",
            }
    return {}


def risk_denial_evidence(history: List[Dict]) -> Dict:
    suicide_question_keywords = [
        "自杀",
        "轻生",
        "不想活",
        "活着没意思",
        "结束生命",
        "想过死",
        "想死",
        "伤害自己",
        "自伤",
        "自残",
        "寻死",
        "想不开",
    ]
    suicide_denial_keywords = [
        "没有自杀",
        "没想过自杀",
        "没有轻生",
        "没想过轻生",
        "没有不想活",
        "没有想过死",
        "没有想死",
        "不想死",
        "不会去死",
        "没有伤害自己",
        "没想过伤害自己",
        "没有自伤",
        "没有自残",
    ]
    plan_denial_keywords = [
        "没有具体计划",
        "没具体计划",
        "没有计划",
        "没计划",
        "没有准备",
        "没准备",
        "不会去做",
        "不会真的做",
        "没有方法",
        "没想好怎么做",
    ]

    for index, item in enumerate(history, start=1):
        question = str(item.get("doctor", ""))
        answer = str(item.get("patient", ""))
        if keyword_matches(question, suicide_question_keywords):
            suicide_denial = keyword_matches(answer, suicide_denial_keywords)
            plan_denial = keyword_matches(answer, plan_denial_keywords)
            if suicide_denial or plan_denial:
                return {
                    "turn": index,
                    "question": question,
                    "patient_answer": answer,
                    "matched": (suicide_denial or plan_denial)[:4],
                    "source": "patient_denial",
                    "note": "患者已明确否认轻生/具体计划，当前不再机械要求追问具体计划。",
                }
    return {}


def top_missing_items(score_result: Dict, limit: int = 4) -> List[str]:
    items = []
    for dimension, value in score_result.items():
        for miss in value.get("miss", []):
            items.append(f"{dimension}：{miss}")
    return items[:limit]


def flatten_score_misses(score_result: Dict, limit: int = 8) -> List[str]:
    misses = []
    for dimension, value in score_result.items():
        for item in value.get("miss", []):
            misses.append(f"{dimension}：{item}")
    return misses[:limit]


def suggest_question_for_missing(missing_label: str) -> str:
    item = missing_label.split("：")[-1]
    suggestions = {
        "主诉/主要不适": "你最近最困扰、最想解决的不舒服是什么？",
        "病程时间": "这种情况大概持续多久了，最早从什么时候开始的？",
        "诱因": "开始前有没有明显压力、事件或生活变化？",
        "睡眠": "最近入睡、早醒、多梦和睡眠时长怎么样？",
        "饮食/二便": "最近胃口、大便和小便有没有变化？",
        "躁狂/轻躁狂": "有没有一段时间精力特别旺、睡很少也不困、话变多或花钱冲动？",
        "精神病性症状": "有没有听到别人听不到的声音，或觉得有人监视、议论、伤害你？",
        "躯体疾病": "近期有没有做过甲状腺、贫血等身体方面检查？",
        "药物/物质因素": "最近有没有服药、饮酒、咖啡因增多或其他物质使用？",
        "自杀意念": "情绪最差时有没有想过不想活、轻生或伤害自己？",
        "自伤/冲动": "有没有出现过控制不住想伤害自己或冲动行为？",
        "具体计划": "如果有轻生想法，有没有具体方法、时间、地点或准备？",
        "保护因素": "当你很难受时，哪些人或事情能让你暂时撑住？",
        "共情回应": "听起来这段时间确实很难熬，你愿意慢慢说说最困扰你的事情吗？",
        "鼓励表达": "没关系，你可以慢慢说，我在听。",
        "开放式提问": "你愿意说说最近最困扰你的事情吗？",
        "澄清追问": "这种情况大概从什么时候开始，最近发生得有多频繁？",
        "总结确认": "我总结一下目前的信息，你看是否准确，还有没有遗漏？",
        "尊重与非评判": "如果你愿意，可以按自己的感受慢慢说，没有标准答案。",
        "舌象": "方便描述一下舌头颜色、舌苔厚薄或口干口苦情况吗？",
        "脉象": "之前看中医时有没有提到过脉象，或感觉心慌、胸闷等情况？",
        "寒热汗": "平时怕冷怕热、出汗、盗汗或口干情况怎么样？",
        "总结/诊断思路": "我先总结一下目前信息，你看是否准确，有没有遗漏？",
    }
    return suggestions.get(item, f"可以继续围绕“{item}”补问一个具体问题。")


def generate_supervisor_hint(case: Dict, history: List[Dict], score_result: Dict) -> str:
    if not history:
        required = get_case_required_questions(case)
        first_target = required[0] if required else "主诉/病程/诱因"
        return f"下一步优先：从开放式主诉开始，先覆盖“{first_target}”。建议问：“你最近最困扰的问题是什么？”"

    misses = flatten_score_misses(score_result, limit=3)
    if misses:
        target = misses[0]
        return f"下一步优先补问：{target}。建议直接问：“{suggest_question_for_missing(target)}”"

    return "核心问诊覆盖较好。下一步建议请学生做阶段性总结，再确认风险保护因素和既往用药史。"


def build_supervisor_messages(
    case: Dict,
    history: List[Dict],
    score_result: Dict,
    supervisor_history: List[Dict],
    question: str,
    scale_assessments: Optional[Dict] = None,
) -> List[Dict]:
    dialogue_text = "\n".join(
        [f"医生：{h['doctor']}\n患者：{h['patient']}" for h in history[-10:]]
    )
    supervisor_text = "\n".join(
        [f"学生：{h['student']}\n督导：{h['supervisor']}" for h in supervisor_history[-6:]]
    )
    score_summary = {
        dimension: {
            "score": value.get("score"),
            "weight": value.get("weight"),
            "hit": value.get("hit", []),
            "miss": value.get("miss", []),
            "covered_by_denial": value.get("covered_by_denial", []),
        }
        for dimension, value in score_result.items()
    }
    scale_summary = build_scale_summary(scale_assessments, case, history)

    system_prompt = f"""
你是神志病中医精神心理方向的教学督导Agent，正在和患者Agent共同支持医学生问诊训练。
你能看到当前病例标准信息、学生与患者的对话、规则评分和病例必问点。

【督导原则】
1. 以教学反馈为主，回答学生关于问诊质量、下一步追问、风险筛查、中医四诊和SOAP书写的问题。
2. 可以参考标准病例信息，但不要一上来把完整诊断、证型和标准答案全部揭示给学生。
3. 优先指出已经覆盖了什么、还缺什么、下一步建议问什么。
4. 遇到自伤自杀、精神病性症状、躁狂/双相线索时，强调继续筛查，但不要提供真实诊疗处置。
5. 每次只给一个最关键的下一步建议，尽量用一句可直接照问的问题表达；一般控制在120字以内。
6. 如果学生问评分原因，要说明对应评分维度和证据，不要泛泛鼓励。
7. 本系统仅用于教学训练，不用于真实临床诊疗。

【当前病例】
{json.dumps(prepare_case_for_prompt(case), ensure_ascii=False, indent=2)}

【当前规则评分】
{json.dumps(score_summary, ensure_ascii=False, indent=2)}

【当前量表评估状态】
{json.dumps(scale_summary, ensure_ascii=False, indent=2)}

【病例必问点】
{json.dumps(get_case_required_questions(case), ensure_ascii=False)}
"""

    user_prompt = f"""
【学生-患者问诊记录】
{dialogue_text if dialogue_text else '暂无'}

【既往督导对话】
{supervisor_text if supervisor_text else '暂无'}

【学生本轮向督导提问】
{question}

请以督导Agent身份回答。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def submit_supervisor_question(
    question: str,
    selected_case: Dict,
    score_result: Dict,
    model: str,
    active_chat: Dict,
    save: Optional[Callable[[], None]] = None,
) -> Dict:
    if not question or not question.strip():
        return {"ok": False, "error": "请输入督导问题。"}

    question = question.strip()
    supervisor_history = active_chat.setdefault("supervisor_history", [])
    messages = build_supervisor_messages(
        selected_case,
        active_chat.get("history", []),
        score_result,
        supervisor_history,
        question,
        active_chat.get("scale_assessments"),
    )
    try:
        answer = call_patient_model(messages, model=model, temperature=0.25)
    except ModelCallError as error:
        answer = (
            generate_supervisor_hint(selected_case, active_chat.get("history", []), score_result)
            + "\n\n> 当前模型未连接，以上为规则版督导提示。"
        )
        store.log_event("supervisor_generation_fallback", model=model, error=str(error))

    feedback = {
        "student": question,
        "supervisor": answer,
        "created_at": now_label(),
    }
    supervisor_history.append(feedback)
    active_chat["show_supervisor_history"] = True
    active_chat["open_supervisor_history_once"] = True
    active_chat["supervisor_history_revision"] = active_chat.get("supervisor_history_revision", 0) + 1
    active_chat["supervisor_feedback_page"] = 0
    active_chat["updated_at"] = now_label()
    if save:
        save()
    return {"ok": True, "feedback": feedback}


def score_dialogue(history: List[Dict], case: Optional[Dict] = None) -> Tuple[Dict, Dict]:
    completeness_weight = 20 if case else 25
    communication_weight = 10 if case else 15

    dimensions = {
        "问诊完整性": {
            "weight": completeness_weight,
            "items": {
                "主诉/主要不适": ["哪里不舒服", "主要哪里", "主要问题", "最困扰", "最想解决", "不舒服", "症状", "困扰", "难受"],
                "病程时间": ["多久", "多长时间", "什么时候开始", "从什么时候", "几天", "几周", "几个月", "持续"],
                "诱因": ["诱因", "原因", "压力", "发生什么", "刺激", "工作", "家庭", "事件", "变化", "导火索"],
                "睡眠": ["睡眠", "失眠", "入睡", "早醒", "多梦", "睡得", "睡不着", "醒得早"],
                "饮食/二便": ["食欲", "胃口", "大便", "小便", "饮食", "二便"],
            },
        },
        "鉴别诊断意识": {
            "weight": 20,
            "items": {
                "躁狂/轻躁狂": ["躁狂", "轻躁狂", "兴奋", "话多", "精力特别旺", "精力旺盛", "睡得少也不困", "睡得少", "不用睡", "花钱", "冲动消费", "特别自信", "想法很多", "脑子转得快", "活动增多", "易怒"],
                "精神病性症状": [
                    "幻听", "幻觉", "妄想", "听到声音", "别人听不到的声音",
                    "听到别人听不到", "看见别人看不到", "有人害", "有人要害",
                    "有人想害", "有人监视", "有人议论", "有人伤害你", "别人监视",
                    "别人议论", "别人伤害你", "被害", "被监视", "被议论",
                    "被控制", "有人控制", "有人跟踪", "被跟踪", "怀疑别人",
                    "奇怪想法", "奇怪的想法",
                ],
                "躯体疾病": ["甲状腺", "甲亢", "贫血", "检查", "身体疾病", "内科", "躯体", "激素"],
                "药物/物质因素": ["药", "饮酒", "咖啡", "毒品", "成瘾", "物质", "酒", "安眠药", "抗抑郁"],
            },
        },
        "风险筛查": {
            "weight": 20,
            "items": {
                "自杀意念": [
                    "自杀", "轻生", "不想活", "活着没意思", "活不下去", "结束生命",
                    "想过死", "想死", "死亡", "寻死", "想不开", "消极念头",
                    "消极想法", "极端想法", "不愿意活", "不想继续活",
                ],
                "自伤/冲动": [
                    "伤害自己", "自伤", "自残", "割腕", "割自己", "撞墙", "跳楼",
                    "吞药", "吃很多药", "服药过量", "冲动", "控制不住", "伤人",
                    "冲动行为", "伤害过自己", "划过", "划伤", "小刀", "摔东西",
                ],
                "具体计划": [
                    "具体计划", "有没有计划", "什么计划", "计划过", "准备", "方法",
                    "怎么做", "什么时候做", "在哪里", "地点", "工具", "刀",
                    "绳", "吞药", "服药过量", "吃药自杀", "实施", "安排",
                    "能保证安全吗", "安全承诺",
                ],
                "保护因素": [
                    "家人支持", "家里人支持", "朋友支持", "谁能帮", "谁可以帮",
                    "向谁求助", "求助谁", "联系谁", "陪着你", "牵挂", "舍不得",
                    "保护因素", "撑住", "撑下去", "阻止", "安全计划",
                    "让你活下去", "不去做", "告诉家人",
                ],
            },
        },
        "沟通技巧": {
            "weight": communication_weight,
            "items": {
                "共情回应": [
                    "我能理解", "我理解", "听起来", "确实不容易", "挺不容易",
                    "很难熬", "难受", "辛苦",
                ],
                "鼓励表达": [
                    "慢慢说", "别着急", "不用急", "我在听", "没关系",
                    "愿意说", "方便说", "可以继续说",
                ],
                "开放式提问": [
                    "能不能说说", "可以讲讲", "愿意说说", "具体说说", "展开说说",
                    "最困扰", "发生什么", "怎么样", "哪些", "什么情况", "有什么",
                ],
                "澄清追问": [
                    "具体", "比如", "除了", "还有", "当时", "后来", "然后",
                    "频率", "程度", "什么时候", "多久",
                ],
                "总结确认": [
                    "我总结一下", "总结", "确认一下", "对吗", "有没有遗漏",
                    "我理解的是", "是不是可以理解为", "目前看来",
                ],
                "尊重与非评判": [
                    "按你的感受", "如实说", "没有标准答案", "不用担心说错",
                    "你可以慢慢回忆", "不会评判", "尊重", "不勉强", "如果愿意",
                ],
            },
        },
        "中医辨证信息采集": {
            "weight": 15,
            "items": {
                "情志": ["情绪", "心情", "烦躁", "焦虑", "低落", "叹气", "压力"],
                "舌象": ["舌", "舌苔", "舌质"],
                "脉象": ["脉", "脉象"],
                "寒热汗": ["怕冷", "怕热", "出汗", "盗汗", "口干", "口苦"],
                "饮食二便": ["食欲", "胃口", "大便", "小便", "二便"],
            },
        },
        "初步总结": {
            "weight": 5,
            "items": {
                "总结/诊断思路": ["总结", "判断", "考虑", "诊断", "辨证", "下一步", "目前看来"]
            },
        },
    }

    if case:
        required_items = build_case_required_score_items(case)
        if required_items:
            dimensions["病例必问点覆盖"] = {
                "weight": 10,
                "items": required_items,
            }

    result = {}
    detail = {}
    denial_evidence = risk_denial_evidence(history)
    for dimension, config in dimensions.items():
        hit = []
        miss = []
        evidence = {}
        item_scores = {}
        covered_by_denial = []
        item_score = round(config["weight"] / max(1, len(config["items"])), 1)

        for item, keywords in config["items"].items():
            item_evidence = find_question_evidence(
                history,
                keywords,
                item=item,
                dimension=dimension,
            )
            if dimension == "风险筛查" and item == "具体计划" and not item_evidence and denial_evidence:
                item_evidence = denial_evidence
                covered_by_denial.append(item)

            if item_evidence:
                hit.append(item)
                evidence[item] = item_evidence
                item_scores[item] = item_score
            else:
                miss.append(item)

        ratio = len(hit) / max(1, len(config["items"]))
        score = round(config["weight"] * ratio, 1)
        result[dimension] = {
            "score": score,
            "weight": config["weight"],
            "hit": hit,
            "miss": miss,
            "evidence": evidence,
            "item_scores": item_scores,
            "covered_by_denial": covered_by_denial,
        }
        detail[dimension] = score
    return result, detail


def build_score_event(
    before_score: Dict,
    after_score: Dict,
    question: str,
    patient_answer: str,
    turn_index: int,
) -> Dict:
    new_hits = []
    score_delta = 0.0

    for dimension, after_value in after_score.items():
        before_value = before_score.get(dimension, {})
        before_hits = set(before_value.get("hit", []))
        after_hits = set(after_value.get("hit", []))
        item_scores = after_value.get("item_scores", {})
        evidence = after_value.get("evidence", {})
        covered_by_denial = set(after_value.get("covered_by_denial", []))
        for item in sorted(after_hits - before_hits):
            new_hits.append(
                {
                    "dimension": dimension,
                    "item": item,
                    "score": item_scores.get(item, 0),
                    "evidence": evidence.get(item, {}),
                    "covered_by_denial": item in covered_by_denial,
                }
            )
        dim_delta = float(after_value.get("score", 0) or 0) - float(before_value.get("score", 0) or 0)
        score_delta += dim_delta

    hit_dimensions = []
    for hit in new_hits:
        if hit["dimension"] not in hit_dimensions:
            hit_dimensions.append(hit["dimension"])
    related_missing = []
    for dimension in hit_dimensions:
        for item in after_score.get(dimension, {}).get("miss", []):
            related_missing.append(f"{dimension}：{item}")

    return {
        "turn": turn_index,
        "question": question,
        "patient_answer": patient_answer,
        "score_delta": round(score_delta, 1),
        "new_hits": new_hits,
        "related_missing": related_missing[:4],
        "next_missing": top_missing_items(after_score, limit=3),
        "created_at": now_label(),
    }


def score_event_summary(event: Optional[Dict]) -> Optional[Dict]:
    if not event:
        return None

    new_hits = event.get("new_hits", [])
    if new_hits:
        hit_text = "、".join(
            [
                f"{hit['dimension']} +{hit.get('score', 0):.1f}：{hit['item']}"
                for hit in new_hits[:5]
            ]
        )
    else:
        hit_text = "本轮暂未新增评分点。"

    missing = event.get("related_missing") or event.get("next_missing", [])
    missing_text = "、".join(missing[:3]) if missing else "核心评分点覆盖较好。"
    return {
        "gained": f"{event.get('score_delta', 0):+.1f} 分",
        "newCoverage": hit_text,
        "stillNeeded": missing_text,
    }


def evaluate_training_completion(history: List[Dict], selected_case: Dict, score_result: Dict) -> Dict:
    total_score = round(sum(value["score"] for value in score_result.values()), 1)
    missing = []

    if len(history) < 5:
        missing.append(f"至少完成5轮问诊（当前{len(history)}轮）")
    if total_score < 60:
        missing.append(f"实时评分建议达到60分以上（当前{total_score:.1f}分）")

    completeness = score_result.get("问诊完整性", {})
    for item in ["主诉/主要不适", "病程时间"]:
        if item in completeness.get("miss", []):
            missing.append(f"问诊完整性：{item}")

    risk_result = score_result.get("风险筛查", {})
    risk_level = selected_case.get("risk_level", "")
    if any(key in risk_level for key in ["中", "高", "危", "自杀", "自伤"]):
        if "自杀意念" in risk_result.get("miss", []):
            missing.append("风险筛查：自杀意念")

    tcm_result = score_result.get("中医辨证信息采集", {})
    if len(tcm_result.get("hit", [])) < 2:
        missing.append("中医辨证信息至少覆盖2项（如情志、舌象、脉象、寒热汗、饮食二便）")

    required = score_result.get("病例必问点覆盖")
    required_ratio = None
    if required:
        required_ratio = len(required.get("hit", [])) / max(
            1,
            len(required.get("hit", [])) + len(required.get("miss", [])),
        )
        if required_ratio < 0.5:
            missing.append("病例必问点覆盖率建议达到50%以上")

    return {
        "ready": len(missing) == 0,
        "status": "可提交" if not missing else "继续问诊",
        "missing": missing[:6],
        "totalScore": total_score,
        "turnCount": len(history),
        "requiredRatio": required_ratio,
    }


def generate_rule_feedback(score_result: Dict) -> str:
    total = sum(value["score"] for value in score_result.values())
    strong = []
    weak = []
    for dimension, value in score_result.items():
        ratio = value["score"] / value["weight"] if value["weight"] else 0
        if ratio >= 0.7:
            strong.append(dimension)
        if ratio < 0.5:
            missing = "、".join(value["miss"][:3]) if value["miss"] else "相关内容"
            weak.append(f"{dimension}：建议补充 {missing}")

    next_items = flatten_score_misses(score_result, limit=4)
    if next_items:
        next_lines = [f"优先补问：{next_items[0]}。建议问：“{suggest_question_for_missing(next_items[0])}”"]
        if len(next_items) > 1:
            next_lines.append("备选补问：" + "、".join(next_items[1:4]))
    else:
        next_lines = ["核心问诊覆盖较好，可进入阶段性总结、诊断思路表达和SOAP整理。"]

    return "\n".join(
        [
            f"总分：{total:.1f}/100",
            "",
            "表现亮点：",
            *([f"- {item}较好，说明问诊中已关注该维度。" for item in strong[:3]] or ["- 目前问诊信息较少，建议继续补充核心病史。"]),
            "",
            "主要不足：",
            *([f"- {item}" for item in weak[:4]] or ["- 暂未发现明显短板，可进一步提高问诊系统性。"]),
            "",
            "下一步建议：",
            *[f"- {item}" for item in next_lines],
        ]
    )


def build_scale_panel_data(active_chat: Dict, selected_case: Dict, history: List[Dict]) -> Dict:
    summary = build_scale_summary(active_chat.get("scale_assessments"), selected_case, history)
    assessments = normalize_scale_assessments(active_chat.get("scale_assessments"))
    recommendations = []
    for item in summary.get("recommendations", []):
        key = item["key"]
        scale_summary = summary.get(key, {})
        reference_score = (
            scale_summary.get("legacy_hamd24_reference")
            if key == "hamd17"
            else scale_summary.get("reference_score")
        )
        recommendations.append(
            {
                "key": key,
                "priority": item["priority"],
                "label": CLINICIAN_SCALE_CONFIG[key]["label"],
                "reason": item["reason"],
                "status": scale_summary.get("status", "not_started"),
                "progress": scale_summary.get("progress", 0),
                "totalItems": scale_summary.get("total_items", 0),
                "partialTotal": scale_summary.get("partial_total", 0),
                "total": scale_summary.get("total"),
                "referenceScore": reference_score,
                "difference": scale_summary.get("difference"),
                "evidence": scale_summary.get("evidence", {}),
                "items": scale_items_payload(key, assessments.get(key, {}).get("answers", {})),
            }
        )
    return {
        "recommendations": recommendations,
        "summary": summary,
    }


def option_payload(options: Dict[str, Optional[int]]) -> List[Dict]:
    return [{"label": label, "value": value} for label, value in options.items()]


def scale_items_payload(scale_key: str, answers: Dict) -> List[Dict]:
    if scale_key == "hamd17":
        return [
            {
                "key": item["key"],
                "label": item["label"],
                "description": "",
                "options": option_payload(item["options"]),
                "value": answers.get(item["key"]),
            }
            for item in HAMD17_ITEMS
        ]
    if scale_key == "hama":
        return [
            {
                "key": item["key"],
                "label": item["label"],
                "description": item.get("description", ""),
                "options": option_payload(HAMA_SCORE_OPTIONS),
                "value": answers.get(item["key"]),
            }
            for item in HAMA14_ITEMS
        ]
    return []


def valid_scale_answer_map(scale_key: str) -> Dict[str, set]:
    if scale_key == "hamd17":
        return {
            item["key"]: set(item["options"].values())
            for item in HAMD17_ITEMS
        }
    if scale_key == "hama":
        valid_values = set(HAMA_SCORE_OPTIONS.values())
        return {item["key"]: valid_values for item in HAMA14_ITEMS}
    return {}


def update_scale_assessment(active_chat: Dict, scale_key: str, answers: Dict) -> Dict:
    assessments = normalize_scale_assessments(active_chat.get("scale_assessments"))
    if scale_key not in assessments:
        raise ValueError("未知量表")

    valid_by_key = valid_scale_answer_map(scale_key)
    cleaned_answers = {}
    for item_key, valid_values in valid_by_key.items():
        value = answers.get(item_key)
        if value in valid_values:
            cleaned_answers[item_key] = value

    assessments[scale_key]["answers"] = cleaned_answers
    total = hamd17_total(cleaned_answers) if scale_key == "hamd17" else hama_total(cleaned_answers)
    assessments[scale_key]["status"] = "completed" if total is not None else "in_progress"
    assessments[scale_key]["completed_at"] = timestamp_now() if total is not None else ""
    active_chat["scale_assessments"] = assessments
    active_chat["soap"] = ""
    active_chat["review_report"] = ""
    active_chat["review_report_generated_at"] = ""
    active_chat["updated_at"] = now_label()
    return assessments[scale_key]


def build_case_panel_data(selected_case: Dict) -> Dict:
    extracted_info = selected_case.get("extracted_info", {})
    tcm_info = selected_case.get("tcm_info", {})
    required_questions = get_case_required_questions(selected_case)

    return {
        "requiredQuestions": required_questions
        or ["主诉/病程/诱因", "风险筛查", "舌象脉象"],
        "collectionPoints": [
            {"label": "睡眠", "value": extracted_info.get("sleep", "根据问诊逐步补充")},
            {
                "label": "食欲胃肠",
                "value": extracted_info.get("appetite_gastrointestinal", "根据问诊逐步补充"),
            },
            {"label": "二便", "value": extracted_info.get("urination_defecation", "根据问诊逐步补充")},
        ],
        "tcmPoints": [
            {"label": "舌象", "value": tcm_info.get("tongue", "未填写")},
            {"label": "脉象", "value": tcm_info.get("pulse", "未填写")},
            {"label": "体质", "value": tcm_info.get("constitution", "未填写")},
        ],
        "standardInfo": [
            {"label": "主诉", "value": selected_case.get("chief_complaint", "未填写")},
            {"label": "教学证型", "value": get_case_syndrome(selected_case)},
            {"label": "诊断大类", "value": get_case_diagnosis(selected_case)},
            {"label": "风险", "value": selected_case.get("risk_level", "需进一步评估")},
        ],
        "tongueImages": get_tongue_images(selected_case),
    }


def build_training_review_report(
    active_chat: Dict,
    selected_case: Dict,
    history: List[Dict],
    score_result: Dict,
    completion: Dict,
) -> str:
    total_score = round(sum(value.get("score", 0) for value in score_result.values()), 1)
    required_result = score_result.get("病例必问点覆盖", {})
    risk_result = score_result.get("风险筛查", {})
    tcm_result = score_result.get("中医辨证信息采集", {})
    top_misses = flatten_score_misses(score_result, limit=6)
    next_question = (
        suggest_question_for_missing(top_misses[0])
        if top_misses
        else "可请学生做阶段性总结，并说明诊断、证型和风险判断依据。"
    )
    scale_summary = build_scale_summary(
        active_chat.get("scale_assessments"),
        selected_case,
        history,
    )

    lines = [
        "# 训练闭环综合复盘报告",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"训练状态：{completion.get('status', '继续问诊')}",
        f"问诊轮数：{len(history)} 轮",
        f"综合得分：{total_score:.1f}/100",
        "",
        "## 病例标准对照",
        f"- 病例：{selected_case.get('title', active_chat.get('case_title', '未命名病例'))}",
        f"- 主诉：{selected_case.get('chief_complaint', '未填写')}",
        f"- 诊断大类：{get_case_diagnosis(selected_case)}",
        f"- 中医证型：{get_case_syndrome(selected_case)}",
        f"- 风险等级：{selected_case.get('risk_level', '需进一步评估')}",
        "",
        "## 关键覆盖情况",
        f"- 病例必问点已覆盖：{'、'.join(required_result.get('hit', [])) or '暂无'}",
        f"- 病例必问点待补充：{'、'.join(required_result.get('miss', [])) or '已基本覆盖'}",
        f"- 风险筛查已覆盖：{'、'.join(risk_result.get('hit', [])) or '暂无'}",
        f"- 中医四诊已覆盖：{'、'.join(tcm_result.get('hit', [])) or '暂无'}",
        "",
        "## 下一步建议",
        f"- 建议下一问：{next_question}",
        "",
        "## 量表复盘",
    ]
    for recommendation in scale_summary.get("recommendations", []):
        label = CLINICIAN_SCALE_CONFIG[recommendation["key"]]["label"]
        lines.append(f"- {recommendation['priority']}：{label}。{recommendation['reason']}")
    if completion.get("missing"):
        lines.extend(["", "## 暂未达成条件", *[f"- {item}" for item in completion["missing"]]])
    lines.append("")
    lines.append("本报告用于教学训练复盘，不用于真实临床诊疗。")
    return "\n".join(lines)


def generate_soap(history: List[Dict], case: Dict, model: str, scale_assessments: Optional[Dict] = None) -> str:
    dialogue = "\n".join([f"医生：{item['doctor']}\n患者：{item['patient']}" for item in history])
    scale_summary = build_scale_summary(scale_assessments, case, history)
    messages = [
        {
            "role": "system",
            "content": (
                "你是中医精神心理方向的病历书写教学助手。请根据模拟问诊记录生成教学用SOAP病历，"
                "必须忠于对话，不补写未问出的信息。"
            ),
        },
        {
            "role": "user",
            "content": f"""
【病例信息】
{json.dumps(prepare_case_for_prompt(case), ensure_ascii=False, indent=2)}

【问诊记录】
{dialogue}

【量表状态】
{json.dumps(scale_summary, ensure_ascii=False, indent=2)}

请按 S、O、A、P、关于量表、教学提示 六部分输出。
""",
        },
    ]
    try:
        return call_patient_model(messages, model=model, temperature=0.2)
    except ModelCallError as error:
        store.log_event("soap_generation_fallback", model=model, error=str(error))
        patient_text = "；".join(str(item.get("patient", "")) for item in history[-3:])
        return "\n".join(
            [
                "## S 主观资料",
                patient_text or "尚缺少患者主诉信息。",
                "",
                "## O 客观资料",
                f"舌象：{case.get('tcm_info', {}).get('tongue', '未填写')}；脉象：{case.get('tcm_info', {}).get('pulse', '未填写')}",
                "",
                "## A 评估",
                f"教学诊断大类：{get_case_diagnosis(case)}；中医证型：{get_case_syndrome(case)}。",
                "",
                "## P 计划",
                "继续补全病程、诱因、风险筛查、中医四诊和量表依据。",
                "",
                "## 关于量表",
                "当前为规则版 SOAP 回退文本，量表结论需以本轮逐项教学评分为准。",
                "",
                "## 教学提示",
                "模型服务暂不可用，本段为规则生成草稿，请教师复核。",
            ]
        )


def submit_patient_question(
    question: str,
    selected_case: Dict,
    active_chat: Dict,
    model: Optional[str] = None,
    save: Optional[Callable[[], None]] = None,
) -> Dict:
    if not question or not question.strip():
        return {"ok": False, "error": "请输入问诊问题。"}

    question = question.strip()
    model = model or active_chat.get("model", DEFAULT_MODEL)
    history = active_chat.setdefault("history", [])
    before_score, _detail = score_dialogue(history, selected_case)
    reactivity = patient_reactivity_state(selected_case, history, question)

    messages = build_patient_messages(selected_case, history, question, reactivity=reactivity)
    active_chat["request_state"] = {
        "kind": "patient",
        "status": "running",
        "question": question,
        "patient_reactivity": reactivity,
        "created_at": now_label(),
    }
    if save:
        save()

    try:
        patient_answer = call_patient_model(messages, model=model, temperature=0.55)
    except ModelCallError as error:
        active_chat["request_state"] = {}
        active_chat["pending_patient_retry"] = {
            "question": question,
            "error": str(error),
            "created_at": now_label(),
        }
        if save:
            save()
        store.log_event("patient_generation_failed", model=model, error=str(error))
        return {"ok": False, "error": str(error), "retryable": True}

    record = {
        "doctor": question,
        "patient": patient_answer,
        "patient_reactivity": reactivity,
    }
    if asks_tongue(question):
        tongue_images = get_tongue_images(selected_case)
        if tongue_images:
            record["tongue_images"] = tongue_images

    history.append(record)
    after_score, _detail = score_dialogue(history, selected_case)
    score_event = build_score_event(before_score, after_score, question, patient_answer, len(history))
    record["score_event"] = score_event
    active_chat.setdefault("score_log", []).append(score_event)

    active_chat["training_submitted"] = False
    active_chat["submitted_at"] = ""
    active_chat["completion_snapshot"] = {}
    active_chat["soap"] = ""
    active_chat["review_report"] = ""
    active_chat["review_report_generated_at"] = ""
    active_chat["request_state"] = {}
    active_chat["pending_patient_retry"] = {}
    active_chat["updated_at"] = now_label()
    if active_chat.get("title") == "新问诊":
        active_chat["title"] = question[:16] + ("..." if len(question) > 16 else "")

    if save:
        save()
    store.log_event(
        "patient_generation_succeeded",
        model=model,
        turn=len(history),
        patient_stance=reactivity.get("stance", ""),
        sensitive_topics=",".join(reactivity.get("sensitive_topics", [])),
    )
    return {"ok": True, "record": record}
