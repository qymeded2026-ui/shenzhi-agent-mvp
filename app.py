import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

import requests
import streamlit as st
from openai import OpenAI

APP_TITLE = "神志病AI双智能体临床思维训练系统 MVP"
OLLAMA_URL = "http://localhost:11434/api/chat"

st.set_page_config(page_title=APP_TITLE, layout="wide")


def load_cases() -> List[Dict]:
    cases = []
    for file in sorted(Path("cases").glob("*.json")):
        with open(file, "r", encoding="utf-8") as f:
            case = json.load(f)
            case["_file"] = str(file)
            cases.append(case)
    return cases


def asks_tongue(question: str) -> bool:
    """判断医生是否问到了舌象相关内容。"""
    keywords = ["舌", "舌象", "舌苔", "舌质"]
    return any(k in question for k in keywords)


def prepare_case_for_prompt(case: Dict) -> Dict:
    """给大模型看的病例信息：去掉图片路径，避免患者回答中说出 tongue_images/case_xxx.jpg。"""
    case_for_prompt = json.loads(json.dumps(case, ensure_ascii=False))

    if "_file" in case_for_prompt:
        del case_for_prompt["_file"]

    tcm_info = case_for_prompt.get("tcm_info", {})
    if "tongue_images" in tcm_info:
        del tcm_info["tongue_images"]

    return case_for_prompt


def call_ollama(messages: List[Dict], model: str, temperature: float = 0.4) -> str:
    """
    在线版大模型调用：
    优先调用 DeepSeek API。
    如果没有配置 API Key，则保留原来的 Ollama 本地调用作为备用。
    """

    # 1. 优先使用 DeepSeek API
    try:
        api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
        if api_key:
            client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature
            )

            return response.choices[0].message.content.strip()

    except Exception as e:
        return f"【DeepSeek API调用失败】请检查API Key、余额、网络或模型名称。错误提示：{e}"

    # 2. 如果没有配置 DeepSeek API Key，则备用调用本地 Ollama
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature}
    }

    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception as e:
        return f"【本地模型暂未连接】请确认 Ollama 已启动、模型名称正确。错误提示：{e}"


def build_patient_messages(case: Dict, history: List[Dict], question: str) -> List[Dict]:
    history_text = "\n".join([
        f"医生：{h['doctor']}\n患者：{h['patient']}" for h in history[-8:]
    ])
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
5. 如果医生提问生硬，可以表现出犹豫；如果医生共情，可以更愿意表达。
6. 不要使用“肝郁脾虚证、心脾两虚证、辨证、证型”等专业术语。
7. 如果医生问到舌象，你只能用患者口吻描述舌头颜色、舌苔厚薄等，不要说图片路径。
8. 严禁回答中出现 tongue_images、case_001.jpg、case_002.jpg、图片路径、文件名等内容。
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
        {"role": "user", "content": user_prompt}
    ]


def score_dialogue(history: List[Dict]) -> Tuple[Dict, Dict]:
    """规则评分：稳定、可解释，适合比赛演示。"""
    doctor_text = " ".join([h["doctor"] for h in history])

    dimensions = {
        "问诊完整性": {
            "weight": 25,
            "items": {
                "主诉/主要不适": ["哪里不舒服", "主要", "不舒服", "症状", "困扰"],
                "病程时间": ["多久", "多长时间", "什么时候", "几天", "几周", "几个月"],
                "诱因": ["诱因", "原因", "压力", "发生什么", "刺激", "工作", "家庭"],
                "睡眠": ["睡眠", "失眠", "入睡", "早醒", "多梦"],
                "饮食/二便": ["食欲", "胃口", "大便", "小便", "饮食"]
            }
        },
        "鉴别诊断意识": {
            "weight": 20,
            "items": {
                "躁狂/轻躁狂": ["躁狂", "兴奋", "话多", "精力特别旺盛", "睡得少也不困"],
                "精神病性症状": ["幻听", "幻觉", "妄想", "有人害", "听到声音"],
                "躯体疾病": ["甲状腺", "甲亢", "贫血", "检查", "身体疾病"],
                "药物/物质因素": ["药", "饮酒", "咖啡", "毒品", "成瘾", "物质"]
            }
        },
        "风险筛查": {
            "weight": 20,
            "items": {
                "自杀意念": ["自杀", "轻生", "不想活", "活着没意思", "结束生命"],
                "自伤/冲动": ["伤害自己", "自伤", "割", "冲动", "控制不住"],
                "具体计划": ["计划", "准备", "方法", "实施", "什么时候做"],
                "保护因素": ["家人", "支持", "孩子", "朋友", "谁能帮你"]
            }
        },
        "沟通技巧": {
            "weight": 15,
            "items": {
                "共情安慰": ["理解", "辛苦", "不容易", "我能理解", "慢慢说"],
                "开放式提问": ["能不能说说", "具体", "怎么样", "还有吗", "愿意"],
                "非诱导表达": ["你觉得", "有没有", "是否", "可以告诉我"]
            }
        },
        "中医辨证信息采集": {
            "weight": 15,
            "items": {
                "情志": ["情绪", "心情", "烦躁", "焦虑", "低落", "叹气"],
                "舌象": ["舌", "舌苔", "舌质"],
                "脉象": ["脉", "脉象"],
                "寒热汗": ["怕冷", "怕热", "出汗", "盗汗", "口干"],
                "饮食二便": ["食欲", "胃口", "大便", "小便"]
            }
        },
        "初步总结": {
            "weight": 5,
            "items": {
                "总结/诊断思路": ["总结", "判断", "考虑", "诊断", "辨证", "下一步"]
            }
        }
    }

    result = {}
    detail = {}
    for dim, cfg in dimensions.items():
        hit = []
        miss = []
        for item, kws in cfg["items"].items():
            if any(kw in doctor_text for kw in kws):
                hit.append(item)
            else:
                miss.append(item)
        ratio = len(hit) / max(1, len(cfg["items"]))
        score = round(cfg["weight"] * ratio, 1)
        result[dim] = {"score": score, "weight": cfg["weight"], "hit": hit, "miss": miss}
        detail[dim] = score
    return result, detail


def generate_rule_feedback(score_result: Dict) -> str:
    total = sum(v["score"] for v in score_result.values())
    strong = []
    weak = []
    for dim, v in score_result.items():
        ratio = v["score"] / v["weight"] if v["weight"] else 0
        if ratio >= 0.7:
            strong.append(dim)
        if ratio < 0.5:
            weak.append(f"{dim}：建议补充 {('、'.join(v['miss'][:3])) if v['miss'] else '相关内容'}")

    feedback = f"""
### 总分：{total:.1f}/100

#### 一、表现亮点
{chr(10).join([f"- {x}较好，说明问诊中已关注该维度。" for x in strong[:3]]) if strong else '- 目前问诊信息较少，建议继续补充核心病史。'}

#### 二、主要不足
{chr(10).join([f"- {x}" for x in weak[:4]]) if weak else '- 暂未发现明显短板，可进一步提高问诊系统性。'}

#### 三、下一步建议
- 优先补充风险筛查，特别是自杀意念、自伤行为和具体计划。
- 补充中医四诊信息，尤其是舌象、脉象、寒热、饮食二便。
- 进行必要鉴别诊断，如躁狂/轻躁狂、精神病性症状、甲状腺问题和药物因素。

> 本评分为教学训练用途，不用于真实医疗诊断。
"""
    return feedback


def generate_soap(history: List[Dict], case: Dict, model: str) -> str:
    dialogue = "\n".join([f"医生：{h['doctor']}\n患者：{h['patient']}" for h in history])
    prompt = f"""
你是一名中医精神心理科教学督导。请根据以下模拟问诊记录，生成教学用SOAP病历。
要求：
1. 仅根据对话中已经问到的信息书写。
2. 对未问到的信息写“未询及”。
3. A部分可结合病例标准答案给出“教学提示”，但要注明“模拟教学”。
4. 不要写成真实处方，不要替代医生诊疗。

【病例标准信息】
{json.dumps(case, ensure_ascii=False, indent=2)}

【问诊记录】
{dialogue}

请按以下格式输出：
S 主观资料：
O 客观资料：
A 评估：
P 计划：
教学提示：
"""
    messages = [{"role": "user", "content": prompt}]
    answer = call_ollama(messages, model=model, temperature=0.2)
    if "本地模型暂未连接" in answer:
        return f"""
### S 主观资料
- 主诉：{case.get('chief_complaint', '未询及')}
- 现病史：根据当前问诊记录整理；若未充分追问，请补充病程、诱因、睡眠、食欲、既往史、家族史。

### O 客观资料
- 舌象：{case.get('tcm_info', {}).get('tongue', '未询及')}
- 脉象：{case.get('tcm_info', {}).get('pulse', '未询及')}

### A 评估
- 模拟教学辨证倾向：{case.get('tcm_info', {}).get('syndrome', '未明确')}
- 风险评估：{case.get('risk_level', '需进一步筛查')}

### P 计划
- 教学建议：继续完善风险筛查、鉴别诊断和中医四诊信息。
- 外治技术提示：{'、'.join(case.get('tcm_info', {}).get('external_therapy', []))}

> Ollama未连接，当前为模板病历。连接本地模型后可自动润色生成。
"""
    return answer


# ---------------- UI ----------------
st.title(APP_TITLE)
st.caption("比赛演示版：患者Agent + 督导Agent + 评分报告 + SOAP病历。仅用于医学教学训练，不用于真实诊疗。")

cases = load_cases()
if not cases:
    st.error("未找到病例文件。请确认 cases 文件夹中有 JSON 病例。")
    st.stop()

with st.sidebar:
    st.header("基础设置")
    model = st.text_input("大模型名称", value="deepseek-v4-flash")
    case_titles = [c["title"] for c in cases]
    selected_title = st.selectbox("选择模拟病例", case_titles)
    selected_case = next(c for c in cases if c["title"] == selected_title)

    if st.button("开始/重置本病例"):
        st.session_state.history = []
        st.session_state.soap = ""
        st.rerun()

    st.divider()
    st.markdown("### 当前病例标准信息")
    st.write(f"主诉：{selected_case.get('chief_complaint')}")
    st.write(f"教学证型：{selected_case.get('tcm_info', {}).get('syndrome')}")
    st.write(f"风险：{selected_case.get('risk_level')}")

if "history" not in st.session_state:
    st.session_state.history = []
if "soap" not in st.session_state:
    st.session_state.soap = ""

left, right = st.columns([2, 1])

with left:
    st.subheader("一、学生问诊区")

    for h in st.session_state.history:
        with st.chat_message("user"):
            st.markdown(h["doctor"])
        with st.chat_message("assistant"):
            st.markdown(h["patient"])

            if h.get("tongue_images"):
                for img in h["tongue_images"]:
                    if os.path.exists(img):
                        st.image(img, caption="当前病例舌象参考图", width=260)
                    else:
                        st.warning(f"未找到舌象图片：{img}")

    question = st.chat_input("请输入你的问诊问题，例如：你最近主要哪里不舒服？")
    if question:
        messages = build_patient_messages(selected_case, st.session_state.history, question)
        patient_answer = call_ollama(messages, model=model, temperature=0.45)

        record = {
            "doctor": question,
            "patient": patient_answer
        }

        if asks_tongue(question):
            tongue_images = selected_case.get("tcm_info", {}).get("tongue_images", [])
            if tongue_images:
                record["tongue_images"] = tongue_images

        st.session_state.history.append(record)
        st.rerun()

with right:
    st.subheader("二、督导实时评分")
    score_result, score_detail = score_dialogue(st.session_state.history)
    total_score = sum(v["score"] for v in score_result.values())
    st.metric("当前总分", f"{total_score:.1f}/100")

    for dim, v in score_result.items():
        st.write(f"**{dim}：{v['score']}/{v['weight']}**")
        st.progress(min(1.0, v["score"] / v["weight"] if v["weight"] else 0))
        if v["miss"]:
            st.caption("待补充：" + "、".join(v["miss"][:3]))

st.divider()

tab1, tab2, tab3 = st.tabs(["评分报告", "SOAP病历", "问诊记录导出"])

with tab1:
    st.subheader("三、自动评分报告")
    if st.button("生成评分报告"):
        st.markdown(generate_rule_feedback(score_result))
    else:
        st.info("完成几轮问诊后，点击按钮生成评分报告。")

with tab2:
    st.subheader("四、自动生成SOAP病历")
    if st.button("生成SOAP病历"):
        st.session_state.soap = generate_soap(st.session_state.history, selected_case, model=model)
    if st.session_state.soap:
        st.markdown(st.session_state.soap)
    else:
        st.info("建议至少完成5轮问诊后再生成病历。")

with tab3:
    st.subheader("五、导出问诊记录")
    export_data = {
        "case": selected_case,
        "history": st.session_state.history,
        "score": score_result
    }
    st.download_button(
        "下载JSON记录",
        data=json.dumps(export_data, ensure_ascii=False, indent=2),
        file_name="dialogue_record.json",
        mime="application/json"
    )
