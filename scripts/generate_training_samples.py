import json
import math
import re
from pathlib import Path

import pandas as pd


ROOT = Path("/Users/qymeded/Documents/神志病AI")
SOURCE_XLSX = Path("/Users/qymeded/Desktop/神志病AI项目训练数据/病例一般信息_标准病例表_可构造训练样本.xlsx")
OUTPUT_DIR = ROOT / "training_samples"


SAMPLE_TYPES = [
    "standard_full_interview",
    "risk_screening_focus",
    "tcm_information_focus",
    "differential_diagnosis_focus",
    "incomplete_interview_for_scoring",
]


def clean(value, default=""):
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    text = str(value).strip()
    if text.lower() == "nan":
        return default
    return text


def clean_number(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        number = float(value)
    except Exception:
        return clean(value)
    return int(number) if number.is_integer() else round(number, 2)


def split_items(text):
    text = clean(text)
    if not text:
        return []
    parts = re.split(r"[，,、；;。\n]+", text)
    return [part.strip() for part in parts if part and part.strip()]


def useful_symptoms(row, limit=5):
    symptoms = split_items(row.get("症状"))
    filtered = [s for s in symptoms if not any(k in s for k in ["舌", "苔", "脉"])]
    return filtered[:limit] or symptoms[:limit]


def has_positive(value):
    return "阳性" in clean(value)


def info_or_unclear(value, unclear_keyword):
    text = clean(value)
    if not text or unclear_keyword in text:
        return ""
    return text


def patient_summary(row):
    symptoms = useful_symptoms(row, 4)
    if symptoms:
        return "最近主要是" + "、".join(symptoms) + "，整个人状态不太好。"
    return clean(row.get("主诉生成文本"), "最近情绪和身体状态都不太好。")


def duration_answer():
    return "具体多久我说不太准，感觉最近这段时间明显些，诱因也不是特别清楚，需要再慢慢回想。"


def sleep_answer(row):
    sleep = info_or_unclear(row.get("睡眠信息_提取"), "未见明确睡眠信息")
    if sleep:
        return f"睡眠方面主要是{sleep}，休息不好以后白天更没精神。"
    return "睡眠这块我没有特别留意清楚，只觉得最近精神状态不太稳定。"


def appetite_bowel_answer(row):
    appetite = info_or_unclear(row.get("食欲胃肠信息_提取"), "未见明确食欲/胃肠信息")
    bowel = info_or_unclear(row.get("二便信息_提取"), "未见明确二便信息")
    parts = []
    if appetite:
        parts.append(f"胃口和胃肠方面主要是{appetite}")
    if bowel:
        parts.append(f"二便方面有{bowel}")
    if parts:
        return "；".join(parts) + "。"
    return "食欲和二便我没有特别清楚的变化，可能还需要再仔细问。"


def risk_answer(row):
    if has_positive(row.get("自伤自杀风险标记")):
        return "情绪特别差的时候，会冒出撑不下去、伤害自己的念头，但具体情况我有点难开口，需要你慢慢问。"
    return "没有明确想过自杀或伤害自己，不过情绪低的时候会觉得很累。"


def plan_answer(row):
    if has_positive(row.get("自伤自杀风险标记")):
        return "目前没有很明确的实施计划，也没有准备什么东西，但这种念头出现时我会害怕。"
    return "没有具体计划，也没有做过准备。家里人或者信任的人能让我稍微稳一点。"


def psychosis_answer(row):
    if has_positive(row.get("精神病性症状标记")):
        return "有时会有一些说不清的异常体验，像是过分担心别人怎么看我，具体还需要你再问细一点。"
    return "没有明显听到别人听不到的声音，也没有觉得有人要害我。"


def bipolar_answer(row):
    if has_positive(row.get("躁狂/双相相关标记")):
        return "有时会有一阵子特别烦躁或精力上来，睡得少也不太困，这方面我自己也分不清。"
    return "没有明显连续几天特别兴奋、话特别多、睡很少也不困的情况。"


def tongue_pulse_answer(row):
    tongue = clean(row.get("舌象"), "舌象不清楚")
    pulse = clean(row.get("脉象"), "脉象不清楚")
    return f"舌头看起来大概是{tongue}。脉象我自己不太会判断，之前摸脉说偏{pulse}。"


def cold_heat_answer():
    return "怕冷怕热、出汗这些我没有特别明显的感觉，可能还需要你再具体问。"


def support_answer():
    return "能慢慢说的时候会好一点，家人或朋友陪着时也会稍微安心些。"


def case_meta(row):
    case_id = clean(row.get("case_id"))
    syndrome = clean(row.get("标准证型")) or clean(row.get("证型"))
    diagnosis = clean(row.get("标准诊断大类")) or clean(row.get("西医诊断"))
    return {
        "case_id": case_id,
        "title": f"{case_id}：{syndrome}",
        "split": clean(row.get("建议拆分")),
        "gender": clean(row.get("性别"), "未填写"),
        "age": clean_number(row.get("年龄")),
        "chief_complaint": clean(row.get("主诉生成文本")),
        "syndrome": syndrome,
        "diagnosis_category": diagnosis,
        "risk_level": clean(row.get("综合风险等级建议")),
        "tongue": clean(row.get("舌象")),
        "pulse": clean(row.get("脉象")),
        "tongue_image": clean(row.get("舌象图片文件名")),
    }


def make_turn(doctor, patient):
    return {"doctor": doctor, "patient": patient}


def build_dialogue(row, sample_type):
    if sample_type == "standard_full_interview":
        return [
            make_turn("你最近主要哪里不舒服？", patient_summary(row)),
            make_turn("这种情况大概多久了？有没有什么诱因？", duration_answer()),
            make_turn("睡眠、食欲和大小便怎么样？", sleep_answer(row) + appetite_bowel_answer(row)),
            make_turn("情绪低落的时候，有没有不想活或者伤害自己的想法？", risk_answer(row)),
            make_turn("有没有幻听、觉得有人害你，或者一段时间特别兴奋、精力特别旺盛？", psychosis_answer(row) + bipolar_answer(row)),
            make_turn("舌象、脉象方便描述一下吗？", tongue_pulse_answer(row)),
            make_turn("我总结一下，你最近情绪和身体状态都受影响，我还会继续评估风险和睡眠饮食，对吗？", "嗯，差不多是这样，你这样说我能理解。"),
        ]
    if sample_type == "risk_screening_focus":
        return [
            make_turn("你最近最困扰的是什么？", patient_summary(row)),
            make_turn("情绪最差的时候，有没有想过轻生或伤害自己？", risk_answer(row)),
            make_turn("这些念头有没有具体计划、方法，或者做过准备？", plan_answer(row)),
            make_turn("身边有没有家人朋友能支持你，或者让你暂时安全一点？", support_answer()),
            make_turn("有没有幻听、妄想，或者突然精力异常旺盛的阶段？", psychosis_answer(row) + bipolar_answer(row)),
            make_turn("睡眠最近怎么样？", sleep_answer(row)),
        ]
    if sample_type == "tcm_information_focus":
        return [
            make_turn("能不能说说最近的心情和身体不舒服？", patient_summary(row)),
            make_turn("情绪变化和压力、胸闷叹气、烦躁这些有关吗？", "情绪确实受影响，有时候会低落或烦躁，压力大时更明显。"),
            make_turn("睡眠、胃口、大便小便这些怎么样？", sleep_answer(row) + appetite_bowel_answer(row)),
            make_turn("有没有怕冷怕热、口干、出汗这些情况？", cold_heat_answer()),
            make_turn("舌头和脉象情况能描述一下吗？", tongue_pulse_answer(row)),
            make_turn("我先按你说的这些做个中医四诊信息整理，可以吗？", "可以，我也希望你帮我慢慢理清楚。"),
        ]
    if sample_type == "differential_diagnosis_focus":
        return [
            make_turn("你最近主要有哪些症状？", patient_summary(row)),
            make_turn("有没有连续几天特别兴奋、话多、花钱冲动，睡得少也不困？", bipolar_answer(row)),
            make_turn("有没有听到别人听不到的声音，或者觉得有人要害你？", psychosis_answer(row)),
            make_turn("最近有没有饮酒、服药、咖啡因增多，或甲状腺、贫血之类身体问题？", "这些我没有特别明确的情况，如果需要可以再做检查确认。"),
            make_turn("有没有不想活、自伤或冲动控制不住的情况？", risk_answer(row)),
            make_turn("睡眠和食欲怎么样？", sleep_answer(row) + appetite_bowel_answer(row)),
        ]
    return [
        make_turn("你最近哪里不舒服？", patient_summary(row)),
        make_turn("睡眠怎么样？", sleep_answer(row)),
        make_turn("胃口怎么样？", appetite_bowel_answer(row)),
        make_turn("舌头看起来怎么样？", tongue_pulse_answer(row)),
    ]


def score_dialogue(dialogue):
    doctor_text = " ".join(turn["doctor"] for turn in dialogue)
    dimensions = {
        "问诊完整性": {
            "weight": 25,
            "items": {
                "主诉/主要不适": ["哪里不舒服", "主要", "不舒服", "症状", "困扰"],
                "病程时间": ["多久", "多长时间", "什么时候", "几天", "几周", "几个月"],
                "诱因": ["诱因", "原因", "压力", "发生什么", "刺激", "工作", "家庭"],
                "睡眠": ["睡眠", "失眠", "入睡", "早醒", "多梦"],
                "饮食/二便": ["食欲", "胃口", "大便", "小便", "饮食"],
            },
        },
        "鉴别诊断意识": {
            "weight": 20,
            "items": {
                "躁狂/轻躁狂": ["躁狂", "兴奋", "话多", "精力特别旺盛", "睡得少也不困"],
                "精神病性症状": ["幻听", "幻觉", "妄想", "有人害", "听到声音"],
                "躯体疾病": ["甲状腺", "甲亢", "贫血", "检查", "身体疾病"],
                "药物/物质因素": ["药", "饮酒", "咖啡", "毒品", "成瘾", "物质"],
            },
        },
        "风险筛查": {
            "weight": 20,
            "items": {
                "自杀意念": ["自杀", "轻生", "不想活", "活着没意思", "结束生命"],
                "自伤/冲动": ["伤害自己", "自伤", "割", "冲动", "控制不住"],
                "具体计划": ["计划", "准备", "方法", "实施", "什么时候做"],
                "保护因素": ["家人", "支持", "孩子", "朋友", "谁能帮你"],
            },
        },
        "沟通技巧": {
            "weight": 15,
            "items": {
                "共情安慰": ["理解", "辛苦", "不容易", "我能理解", "慢慢说"],
                "开放式提问": ["能不能说说", "具体", "怎么样", "还有吗", "愿意"],
                "非诱导表达": ["你觉得", "有没有", "是否", "可以告诉我"],
            },
        },
        "中医辨证信息采集": {
            "weight": 15,
            "items": {
                "情志": ["情绪", "心情", "烦躁", "焦虑", "低落", "叹气"],
                "舌象": ["舌", "舌苔", "舌质"],
                "脉象": ["脉", "脉象"],
                "寒热汗": ["怕冷", "怕热", "出汗", "盗汗", "口干"],
                "饮食二便": ["食欲", "胃口", "大便", "小便"],
            },
        },
        "初步总结": {
            "weight": 5,
            "items": {"总结/诊断思路": ["总结", "判断", "考虑", "诊断", "辨证", "下一步"]},
        },
    }
    result = {}
    for dim, cfg in dimensions.items():
        hit, miss = [], []
        for item, keywords in cfg["items"].items():
            (hit if any(keyword in doctor_text for keyword in keywords) else miss).append(item)
        score = round(cfg["weight"] * len(hit) / max(1, len(cfg["items"])), 1)
        result[dim] = {"score": score, "weight": cfg["weight"], "hit": hit, "miss": miss}
    return result


def asked(dialogue, keywords):
    text = " ".join(turn["doctor"] for turn in dialogue)
    return any(keyword in text for keyword in keywords)


def soap_reference(row, dialogue):
    meta = case_meta(row)
    sleep = info_or_unclear(row.get("睡眠信息_提取"), "未见明确睡眠信息")
    appetite = info_or_unclear(row.get("食欲胃肠信息_提取"), "未见明确食欲/胃肠信息")
    bowel = info_or_unclear(row.get("二便信息_提取"), "未见明确二便信息")
    subjective = {
        "主诉": meta["chief_complaint"] if asked(dialogue, ["哪里不舒服", "困扰", "症状", "不舒服"]) else "未询及",
        "病程/诱因": "患者表示时间及诱因需进一步追问确认" if asked(dialogue, ["多久", "诱因", "原因"]) else "未询及",
        "睡眠": sleep if asked(dialogue, ["睡眠", "失眠", "早醒", "多梦"]) and sleep else "未询及",
        "食欲胃肠": appetite if asked(dialogue, ["食欲", "胃口"]) and appetite else "未询及",
        "二便": bowel if asked(dialogue, ["大便", "小便", "二便"]) and bowel else "未询及",
        "风险": clean(row.get("自伤自杀风险标记")) if asked(dialogue, ["自杀", "轻生", "伤害自己", "自伤", "不想活"]) else "未询及",
        "鉴别": {
            "精神病性症状": clean(row.get("精神病性症状标记")) if asked(dialogue, ["幻听", "幻觉", "妄想", "有人害"]) else "未询及",
            "躁狂/双相线索": clean(row.get("躁狂/双相相关标记")) if asked(dialogue, ["躁狂", "兴奋", "话多", "精力"]) else "未询及",
        },
    }
    objective = {
        "舌象": meta["tongue"] if asked(dialogue, ["舌"]) else "未询及",
        "脉象": meta["pulse"] if asked(dialogue, ["脉"]) else "未询及",
    }
    return {
        "S": subjective,
        "O": objective,
        "A": {
            "模拟教学辨证倾向": meta["syndrome"],
            "标准诊断大类": meta["diagnosis_category"],
            "风险等级建议": meta["risk_level"],
        },
        "P": [
            "继续完善风险筛查，尤其是自杀意念、自伤行为、具体计划和保护因素。",
            "补充精神病性症状、躁狂/轻躁狂、躯体疾病和药物物质因素鉴别。",
            "完善中医四诊信息，结合舌象、脉象、情志、睡眠、饮食二便进行教学辨证。",
        ],
        "teaching_note": "本记录为模拟教学参考，不用于真实诊疗或处方。",
    }


def supervisor_reference(row, dialogue):
    scores = score_dialogue(dialogue)
    total = round(sum(item["score"] for item in scores.values()), 1)
    weak_dims = [
        f"{dim}：建议补充{'、'.join(value['miss'][:3])}"
        for dim, value in scores.items()
        if value["miss"] and value["score"] / value["weight"] < 0.7
    ]
    return {
        "score_result": scores,
        "total_score": total,
        "required_questions": split_items(row.get("必问点建议")),
        "main_gaps": weak_dims,
        "ideal_next_questions": [
            "有没有不想活或伤害自己的想法？有没有具体计划？",
            "有没有幻听、妄想，或一段时间特别兴奋、精力旺盛？",
            "睡眠、食欲、大小便、舌象和脉象分别怎么样？",
        ],
        "teaching_warning": "评分仅用于教学训练，不用于真实医疗诊断。",
    }


def patient_system_prompt(row):
    meta = case_meta(row)
    return (
        "你正在扮演一名中医精神心理方向的模拟患者，用于医学生问诊训练。"
        "你必须严格依据病例角色卡回答，不主动透露诊断、证型、量表分数或全部症状。"
        f"病例摘要：性别{meta['gender']}，年龄{meta['age']}，主诉为{meta['chief_complaint']}；"
        f"主要症状包括{'、'.join(useful_symptoms(row, 6))}；"
        f"舌象{meta['tongue']}，脉象{meta['pulse']}。"
    )


def patient_sft_records(row, sample_id, dialogue):
    records = []
    history = []
    for turn_index, turn in enumerate(dialogue, start=1):
        user_content = "既往对话：\n"
        if history:
            user_content += "\n".join(f"医生：{h['doctor']}\n患者：{h['patient']}" for h in history)
        else:
            user_content += "暂无"
        user_content += f"\n\n医生本轮提问：{turn['doctor']}\n请以患者身份自然回答。"
        records.append(
            {
                "sample_id": f"{sample_id}_turn_{turn_index:02d}",
                "case_id": clean(row.get("case_id")),
                "messages": [
                    {"role": "system", "content": patient_system_prompt(row)},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": turn["patient"]},
                ],
            }
        )
        history.append(turn)
    return records


def build_sample(row, sample_index, sample_type):
    meta = case_meta(row)
    dialogue = build_dialogue(row, sample_type)
    sample_id = f"{meta['case_id']}_{sample_index:02d}_{sample_type}"
    return {
        "sample_id": sample_id,
        "case": meta,
        "sample_type": sample_type,
        "dialogue": dialogue,
        "supervisor_reference": supervisor_reference(row, dialogue),
        "soap_reference": soap_reference(row, dialogue),
        "patient_agent_constraints": {
            "speaking_style": clean(row.get("患者说话风格建议")),
            "do_not_reveal": clean(row.get("禁止透露信息")),
        },
    }


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_excel(SOURCE_XLSX, sheet_name="标准病例表")
    all_dialogues = []
    patient_turns = []

    for _, row in df.iterrows():
        for idx, sample_type in enumerate(SAMPLE_TYPES, start=1):
            sample = build_sample(row, idx, sample_type)
            all_dialogues.append(sample)
            patient_turns.extend(patient_sft_records(row, sample["sample_id"], sample["dialogue"]))

    def by_split(rows, split):
        return [row for row in rows if row["case"]["split"] == split]

    train_dialogues = by_split(all_dialogues, "训练集")
    val_dialogues = by_split(all_dialogues, "验证集")
    train_turns = [r for r in patient_turns if next(s for s in all_dialogues if s["sample_id"] == "_".join(r["sample_id"].split("_")[:-2]))["case"]["split"] == "训练集"]
    val_turns = [r for r in patient_turns if next(s for s in all_dialogues if s["sample_id"] == "_".join(r["sample_id"].split("_")[:-2]))["case"]["split"] == "验证集"]

    write_jsonl(OUTPUT_DIR / "train_dialogues.jsonl", train_dialogues)
    write_jsonl(OUTPUT_DIR / "val_dialogues.jsonl", val_dialogues)
    write_jsonl(OUTPUT_DIR / "all_dialogues.jsonl", all_dialogues)
    write_jsonl(OUTPUT_DIR / "train_patient_agent_sft.jsonl", train_turns)
    write_jsonl(OUTPUT_DIR / "val_patient_agent_sft.jsonl", val_turns)

    write_jsonl(
        OUTPUT_DIR / "train_supervisor_refs.jsonl",
        [{"sample_id": s["sample_id"], "case_id": s["case"]["case_id"], **s["supervisor_reference"]} for s in train_dialogues],
    )
    write_jsonl(
        OUTPUT_DIR / "val_supervisor_refs.jsonl",
        [{"sample_id": s["sample_id"], "case_id": s["case"]["case_id"], **s["supervisor_reference"]} for s in val_dialogues],
    )
    write_jsonl(
        OUTPUT_DIR / "train_soap_refs.jsonl",
        [{"sample_id": s["sample_id"], "case_id": s["case"]["case_id"], "soap_reference": s["soap_reference"]} for s in train_dialogues],
    )
    write_jsonl(
        OUTPUT_DIR / "val_soap_refs.jsonl",
        [{"sample_id": s["sample_id"], "case_id": s["case"]["case_id"], "soap_reference": s["soap_reference"]} for s in val_dialogues],
    )

    manifest = {
        "source": str(SOURCE_XLSX),
        "output_dir": str(OUTPUT_DIR),
        "cases": int(len(df)),
        "sample_types": SAMPLE_TYPES,
        "dialogue_samples": {
            "train": len(train_dialogues),
            "val": len(val_dialogues),
            "all": len(all_dialogues),
        },
        "patient_agent_sft_turns": {
            "train": len(train_turns),
            "val": len(val_turns),
            "all": len(patient_turns),
        },
        "schema_note": "所有样本均为脱敏模拟教学数据，不用于真实诊疗。",
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
