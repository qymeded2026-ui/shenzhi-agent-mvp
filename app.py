import base64
import json
import os
import random
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import requests
import streamlit as st
from openai import OpenAI

APP_TITLE = "神志思训"
OLLAMA_URL = "http://localhost:11434/api/chat"

st.set_page_config(page_title="神志思训", layout="wide")


def inject_custom_css():
    """注入页面与侧边栏样式，让左侧栏更接近现代AI应用。"""
    st.markdown(
        """
        <style>
        /* 整体页面 */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }

        /* 左侧栏背景 */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #F7FBFA 0%, #F8FAFC 46%, #FFFFFF 100%);
            border-right: 1px solid rgba(27, 75, 86, 0.10);
        }

        [data-testid="stSidebar"] > div:first-child {
            padding-top: 1.15rem;
        }

        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 0.38rem;
        }

        /* 侧栏极简Logo */
        .sidebar-logo {
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 0.35rem 0 1.15rem 0;
            margin-bottom: 0.6rem;
            border-bottom: 1px solid rgba(27, 75, 86, 0.08);
        }

        .sidebar-logo img {
            width: 7.6rem;
            max-width: 88%;
            height: auto;
            display: block;
        }

        /* 侧栏品牌区 */
        .sidebar-brand {
            padding: 0.35rem 0.15rem 0.85rem 0.15rem;
            border-bottom: 1px solid rgba(27, 75, 86, 0.08);
            margin-bottom: 0.55rem;
        }

        .sidebar-brand-title {
            font-size: 1.35rem;
            line-height: 1.2;
            font-weight: 800;
            letter-spacing: 0.10em;
            color: #123B46;
        }

        .sidebar-brand-subtitle {
            margin-top: 0.28rem;
            font-size: 0.76rem;
            color: #6B7280;
            letter-spacing: 0.02em;
        }

        .sidebar-section-label {
            margin: 0.85rem 0 0.25rem 0.12rem;
            font-size: 0.74rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            color: #7C8A91;
        }

        .sidebar-meta {
            font-size: 0.70rem;
            color: #7A8790;
            margin: -0.28rem 0 0.38rem 0.78rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 13.8rem;
        }

        .sidebar-footer {
            margin-top: 1.15rem;
            padding: 0.72rem 0.78rem;
            border-radius: 0.95rem;
            background: rgba(231, 245, 242, 0.65);
            border: 1px solid rgba(31, 113, 108, 0.10);
            color: #587078;
            font-size: 0.72rem;
            line-height: 1.55;
        }

        /* 侧栏按钮：统一改成AI应用的圆角列表项 */
        [data-testid="stSidebar"] .stButton > button {
            justify-content: flex-start;
            text-align: left;
            min-height: 2.35rem;
            padding: 0.55rem 0.72rem;
            border-radius: 0.88rem;
            border: 1px solid transparent;
            background: transparent;
            color: #263238;
            font-weight: 500;
            transition: all 0.16s ease;
            box-shadow: none;
        }

        [data-testid="stSidebar"] .stButton > button:hover {
            background: rgba(228, 241, 239, 0.92);
            border-color: rgba(31, 113, 108, 0.13);
            color: #123B46;
            transform: translateY(-1px);
        }

        [data-testid="stSidebar"] .stButton > button:focus:not(:active) {
            border-color: rgba(31, 113, 108, 0.30);
            box-shadow: 0 0 0 0.12rem rgba(31, 113, 108, 0.08);
        }

        /* 新建问诊按钮 */
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            justify-content: center;
            background: linear-gradient(135deg, #174C5B 0%, #2A7B73 100%);
            color: #FFFFFF;
            border: 0;
            font-weight: 700;
            box-shadow: 0 8px 22px rgba(23, 76, 91, 0.18);
        }

        [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, #123B46 0%, #246B64 100%);
            color: #FFFFFF;
            transform: translateY(-1px);
        }

        /* 搜索框 */
        [data-testid="stSidebar"] input {
            border-radius: 0.86rem !important;
            border: 1px solid rgba(27, 75, 86, 0.12) !important;
            background: rgba(255, 255, 255, 0.86) !important;
        }

        /* 聊天区顶部当前病例提示 */
        .current-case-pill {
            display: inline-block;
            padding: 0.42rem 0.72rem;
            border-radius: 999px;
            background: #F1F8F7;
            color: #2A625E;
            border: 1px solid rgba(42, 98, 94, 0.12);
            font-size: 0.80rem;
            margin-bottom: 0.35rem;
        }

        /* 督导工作台 */
        .supervisor-hero {
            padding: 0.85rem 0.95rem;
            border: 1px solid rgba(28, 92, 92, 0.14);
            border-left: 4px solid #2A7B73;
            border-radius: 8px;
            background: #F8FCFB;
            margin-bottom: 0.75rem;
        }
        .supervisor-hero-title {
            font-size: 1.02rem;
            font-weight: 800;
            color: #123B46;
            line-height: 1.35;
        }
        .supervisor-hero-subtitle {
            margin-top: 0.18rem;
            font-size: 0.76rem;
            color: #647179;
            line-height: 1.5;
        }
        .agent-flow {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 0.35rem;
            margin: 0.55rem 0 0.75rem 0;
        }
        .agent-flow-step {
            border: 1px solid rgba(42, 98, 94, 0.13);
            border-radius: 8px;
            background: #FFFFFF;
            padding: 0.45rem 0.38rem;
            text-align: center;
            color: #31515A;
            font-size: 0.72rem;
            font-weight: 700;
            line-height: 1.25;
        }
        .supervisor-panel {
            border: 1px solid rgba(31, 113, 108, 0.14);
            border-radius: 8px;
            background: #FFFFFF;
            padding: 0.85rem 0.9rem;
            margin-bottom: 0.72rem;
            box-shadow: 0 8px 20px rgba(20, 70, 80, 0.045);
        }
        .supervisor-panel-title {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem;
            margin-bottom: 0.55rem;
            color: #123B46;
            font-size: 0.92rem;
            font-weight: 800;
        }
        .supervisor-panel-kicker {
            color: #6F7D84;
            font-size: 0.70rem;
            font-weight: 700;
            letter-spacing: 0.05em;
        }
        .score-dashboard {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.55rem;
            margin-bottom: 0.55rem;
        }
        .score-tile {
            border-radius: 8px;
            border: 1px solid rgba(42, 98, 94, 0.10);
            background: #F8FBFA;
            padding: 0.58rem 0.62rem;
        }
        .score-value {
            font-size: 1.28rem;
            font-weight: 850;
            color: #174C5B;
            line-height: 1.15;
        }
        .score-label {
            margin-top: 0.16rem;
            color: #6B7880;
            font-size: 0.72rem;
            line-height: 1.25;
        }
        .next-step-box {
            border-left: 3px solid #A96B2C;
            background: #FFF9F1;
            color: #4D4235;
            border-radius: 8px;
            padding: 0.68rem 0.75rem;
            line-height: 1.55;
            font-size: 0.84rem;
        }
        .target-list {
            margin: 0.35rem 0 0 0;
            padding-left: 1.05rem;
            color: #334A52;
            font-size: 0.82rem;
            line-height: 1.58;
        }
        .agent-bubble-student,
        .agent-bubble-supervisor {
            border-radius: 8px;
            padding: 0.55rem 0.65rem;
            margin-bottom: 0.45rem;
            line-height: 1.55;
            font-size: 0.82rem;
        }
        .agent-bubble-student {
            background: #F3F6F8;
            border: 1px solid rgba(75, 91, 102, 0.12);
            color: #2F3E46;
        }
        .agent-bubble-supervisor {
            background: #F1F8F7;
            border: 1px solid rgba(31, 113, 108, 0.14);
            color: #244D52;
        }
        .compact-caption {
            color: #6F7D84;
            font-size: 0.74rem;
            line-height: 1.5;
        }
        .student-chat-empty {
            min-height: 390px;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            border: 0;
            background: transparent;
            color: #8A969C;
            font-size: 0.86rem;
            margin: 0;
            padding: 1.1rem;
        }
        .student-chat-spacer {
            min-height: 1rem;
        }
        .student-composer-label {
            color: #6F7D84;
            font-size: 0.74rem;
            font-weight: 700;
            letter-spacing: 0.05em;
            margin: 0.35rem 0 0.2rem 0.05rem;
        }
        .agent-trace-item {
            color: #5F6F76;
            font-size: 0.78rem;
            line-height: 1.5;
            margin: 0.16rem 0;
        }
        div[data-testid="stForm"] {
            border-radius: 8px;
            border-color: rgba(42, 98, 94, 0.13);
        }
        div[data-testid="stForm"] input {
            min-height: 3rem;
        }

        /* 弱化默认分割线 */
        hr {
            margin: 0.8rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def read_svg_as_data_uri(path: str) -> str:
    svg = Path(path).read_text(encoding="utf-8")
    encoded = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{encoded}"


def load_cases() -> List[Dict]:
    cases = []
    for file in sorted(Path("cases").glob("*.json")):
        with open(file, "r", encoding="utf-8") as f:
            case = json.load(f)
            case["_file"] = str(file)
            cases.append(case)
    return cases


def get_case_title(case: Dict) -> str:
    return case.get("title", case.get("case_id", "未命名病例"))


def get_case_syndrome(case: Dict) -> str:
    return case.get("tcm_info", {}).get("syndrome", "未填写")


def get_case_diagnosis(case: Dict) -> str:
    return case.get("western_diagnosis", {}).get("category", "未填写")


def get_case_risk(case: Dict) -> str:
    return case.get("risk_level", "需进一步评估")


def unique_case_values(cases: List[Dict], getter) -> List[str]:
    values = {getter(case) for case in cases if getter(case)}
    return sorted(values)


def filter_cases_by_facets(
    cases: List[Dict],
    syndrome_filter: str,
    diagnosis_filter: str,
    risk_filter: str,
) -> List[Dict]:
    filtered = []
    for case in cases:
        if syndrome_filter != "全部" and get_case_syndrome(case) != syndrome_filter:
            continue
        if diagnosis_filter != "全部" and get_case_diagnosis(case) != diagnosis_filter:
            continue
        if risk_filter != "全部" and get_case_risk(case) != risk_filter:
            continue
        filtered.append(case)
    return filtered


def count_cases_with_tongue_images(cases: List[Dict]) -> int:
    return sum(1 for case in cases if get_tongue_images(case))


def get_case_required_questions(case: Dict) -> List[str]:
    questions = case.get("teaching_info", {}).get("required_questions", [])
    return questions if isinstance(questions, list) else []


def required_question_keywords(item: str) -> List[str]:
    keyword_map = {
        "主诉/病程/诱因": ["哪里不舒服", "主要", "不舒服", "症状", "困扰", "多久", "什么时候", "诱因", "原因", "压力"],
        "睡眠/食欲/二便": ["睡眠", "失眠", "入睡", "早醒", "多梦", "食欲", "胃口", "大便", "小便", "二便", "饮食"],
        "自伤自杀风险": ["自杀", "轻生", "不想活", "活着没意思", "伤害自己", "自伤", "结束生命"],
        "幻听妄想": ["幻听", "幻觉", "妄想", "有人害", "听到声音"],
        "躁狂或轻躁狂": ["躁狂", "轻躁狂", "兴奋", "话多", "精力", "睡得少也不困"],
        "舌象脉象": ["舌", "舌象", "舌苔", "舌质", "脉", "脉象"],
        "既往史/用药史/家族史": ["既往", "以前", "用药", "药物", "吃药", "家族", "家人", "遗传", "病史"],
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


def reset_chat_for_case(active_chat: Dict, case_title: str, model: str):
    active_chat["model"] = model
    active_chat["case_title"] = case_title
    active_chat["history"] = []
    active_chat["supervisor_history"] = []
    active_chat["soap"] = ""
    active_chat["title"] = "新问诊"
    active_chat["updated_at"] = datetime.now().strftime("%m-%d %H:%M")


def render_case_library_status(cases: List[Dict]):
    st.markdown("### 病例库驱动训练")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("训练状态", "已接入")
    col2.metric("病例角色卡", f"{len(cases)}例")
    col3.metric("覆盖证型", f"{len(unique_case_values(cases, get_case_syndrome))}类")
    col4.metric("舌象匹配", f"{count_cases_with_tongue_images(cases)}/{len(cases)}")


def render_home_header():
    """首页头图展示。"""
    banner_path = "assets/home_banner.png"

    if os.path.exists(banner_path):
        # 用中间列控制头图宽度，避免首页横幅过大。
        left, center, right = st.columns([1.3, 5, 1.3])
        with center:
            st.image(banner_path, use_container_width=True)
    else:
        st.markdown(
            """
            # 神志思训
            ### 神志病智能问诊与临床思维训练平台

            本系统基于脱敏病例库构建，融合患者Agent、督导Agent、舌象图像展示、评分反馈与SOAP病历生成，
            面向中医神志病教学场景，帮助学习者在模拟问诊中训练临床思维、辨证能力与病历书写能力。

            > 仅用于医学教学训练与竞赛演示，不用于真实临床诊疗。
            """
        )


def render_case_library_overview():
    """病例库概览展示模块，用于比赛展示，不影响问诊流程。"""

    st.markdown("## 病例库概览")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("脱敏病例总量", "234例")
    col2.metric("上线教学病例", "25例")
    col3.metric("覆盖证型", "7类")
    col4.metric("数据维度", "10+项")

    st.markdown("### 一、病例库构成")
    st.markdown(
        """
        本系统基于234例脱敏神志病相关病例构建专科教学病例库，
        将原始病例中的基本信息、量表评分、症状表现、舌象、脉象、
        体质、证型及西医诊断等内容进行结构化处理，
        形成可被患者Agent调用的病例角色卡和可被督导Agent调用的教学评价依据。
        """
    )

    st.markdown("### 二、主要证型分布")
    syndrome_data = {
        "证型": [
            "肝郁脾虚证",
            "心脾两虚证",
            "肝气郁结证",
            "痰气郁结证",
            "心神失养证",
            "气郁化火证",
            "心肾阴虚证",
        ],
        "病例数": [87, 36, 34, 32, 30, 11, 4],
    }
    st.dataframe(syndrome_data, use_container_width=True)

    st.markdown("### 三、高频症状特征")
    st.markdown(
        """
        高频症状主要包括：心境低落、失眠、兴趣减退、食欲不振、焦虑、
        情绪不稳、乏力、烦躁不安、胸部满闷、头痛、表情淡漠、头晕等。
        这些症状被用于构建患者Agent的问诊回答逻辑，并作为督导Agent评价学生问诊完整性的依据。
        """
    )

    st.markdown("### 四、舌象与脉象特征")
    st.markdown(
        """
        病例库纳入了舌象和脉象信息。常见舌象包括舌红苔白腻、舌红苔黄腻、
        舌淡红苔薄白、舌红苔薄白等；常见脉象包括弦细、弦滑、弦、滑数、细等。
        系统采用“具体病例—具体舌象图片”的绑定方式，避免将某一证型机械对应到单一舌象。
        """
    )

    st.markdown("### 五、病例库构建流程")
    st.markdown(
        """
        脱敏病例资料 → 字段标准化 → 症状/舌脉/量表/证型结构化 → 
        生成病例角色卡 → 患者Agent调用 → 督导Agent评分反馈 → 
        SOAP病历生成与教学复盘。
        """
    )


# ---------------- 多问诊会话管理 ----------------
def create_new_chat(default_case_title: str):
    """创建一个新的问诊会话。"""
    chat_id = str(uuid.uuid4())[:8]

    now = datetime.now().strftime("%m-%d %H:%M")
    st.session_state.chat_sessions[chat_id] = {
        "title": "新问诊",
        "case_title": default_case_title,
        "model": st.session_state.get("default_model", "deepseek-v4-flash"),
        "history": [],
        "supervisor_history": [],
        "soap": "",
        "created_at": now,
        "updated_at": now,
    }

    st.session_state.active_chat_id = chat_id


def init_chat_sessions(default_case_title: str):
    """初始化问诊会话。"""
    if "default_model" not in st.session_state:
        st.session_state.default_model = "deepseek-v4-flash"

    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = {}
        create_new_chat(default_case_title)

    if "active_chat_id" not in st.session_state:
        first_id = list(st.session_state.chat_sessions.keys())[0]
        st.session_state.active_chat_id = first_id


def get_active_chat() -> Dict:
    """获取当前正在进行的问诊会话。"""
    return st.session_state.chat_sessions[st.session_state.active_chat_id]


def render_chat_sidebar(default_case_title: str):
    """左侧栏：ChatGPT风格的问诊记录列表。"""
    with st.sidebar:
        logo_path = "assets/shenzhi_logo_minimal.svg"
        if os.path.exists(logo_path):
            st.markdown(
                f"<div class='sidebar-logo'><img src='{read_svg_as_data_uri(logo_path)}' alt='神志思训 logo'></div>",
                unsafe_allow_html=True,
            )

        if st.button("＋  新建问诊", type="primary", use_container_width=True):
            create_new_chat(default_case_title)
            st.rerun()

        search_text = st.text_input(
            "搜索问诊记录",
            placeholder="搜索问诊记录...",
            label_visibility="collapsed",
            key="sidebar_chat_search",
        ).strip()

        st.markdown("<div class='sidebar-section-label'>近期问诊</div>", unsafe_allow_html=True)

        chat_items = list(st.session_state.chat_sessions.items())[::-1]
        if search_text:
            chat_items = [
                (chat_id, chat)
                for chat_id, chat in chat_items
                if search_text in chat.get("title", "")
                or search_text in chat.get("case_title", "")
            ]

        if not chat_items:
            st.caption("暂无匹配的问诊记录。")

        for chat_id, chat in chat_items:
            is_active = chat_id == st.session_state.active_chat_id
            title = chat.get("title", "新问诊")
            case_title = chat.get("case_title", "")
            updated_at = chat.get("updated_at") or chat.get("created_at", "")

            # Streamlit的按钮无法直接放HTML，因此用符号弱化“按钮感”，接近聊天应用侧栏。
            prefix = "●" if is_active else "  "
            label = f"{prefix} {title}"

            if st.button(label, key=f"open_chat_{chat_id}", use_container_width=True):
                st.session_state.active_chat_id = chat_id
                st.rerun()

            meta_parts = []
            if case_title:
                meta_parts.append(case_title)
            if updated_at:
                meta_parts.append(updated_at)
            if meta_parts:
                st.markdown(
                    f"<div class='sidebar-meta'>{' ｜ '.join(meta_parts)}</div>",
                    unsafe_allow_html=True,
                )

        st.markdown("<div class='sidebar-section-label'>管理</div>", unsafe_allow_html=True)
        with st.expander("当前问诊操作", expanded=False):
            active_id = st.session_state.active_chat_id
            active_sidebar_chat = st.session_state.chat_sessions[active_id]
            rename_title = st.text_input(
                "当前问诊名称",
                value=active_sidebar_chat.get("title", "新问诊"),
                key=f"rename_chat_{active_id}",
            )
            if st.button("保存名称", use_container_width=True, key=f"save_rename_{active_id}"):
                cleaned_title = rename_title.strip() or "新问诊"
                active_sidebar_chat["title"] = cleaned_title[:24]
                active_sidebar_chat["updated_at"] = datetime.now().strftime("%m-%d %H:%M")
                st.rerun()

            st.divider()
            st.caption("删除只会移除当前网页会话中的问诊记录，不影响病例库文件。")
            if st.button("删除当前问诊", use_container_width=True):
                if len(st.session_state.chat_sessions) > 1:
                    del st.session_state.chat_sessions[active_id]
                    st.session_state.active_chat_id = list(st.session_state.chat_sessions.keys())[0]
                    st.rerun()
                else:
                    st.warning("至少保留一个问诊会话。")

        st.markdown(
            """
            <div class="sidebar-footer">
                当前记录仅保存在本次网页会话中。<br/>
                平台仅用于医学教学训练与竞赛演示。
            </div>
            """,
            unsafe_allow_html=True,
        )

def asks_tongue(question: str) -> bool:
    """判断医生是否问到了舌象相关内容。"""
    keywords = ["舌", "舌象", "舌苔", "舌质"]
    return any(k in question for k in keywords)


def get_tongue_images(case: Dict) -> List[str]:
    """
    获取当前病例对应的舌象图片。
    优先读取JSON中的 tcm_info.tongue_images；
    如果没有，则根据 case_id 自动在 tongue_images 文件夹中查找。
    """
    images = case.get("tcm_info", {}).get("tongue_images", [])
    valid_images = []

    for img in images:
        if isinstance(img, str) and os.path.exists(img):
            valid_images.append(img)

    if valid_images:
        return valid_images

    case_id = case.get("case_id", "")
    if not case_id:
        return []

    extensions = [".jpg", ".jpeg", ".png", ".webp", ".JPG", ".JPEG", ".PNG"]
    for ext in extensions:
        candidate = os.path.join("tongue_images", f"{case_id}{ext}")
        if os.path.exists(candidate):
            return [candidate]

    return []


def submit_question(question: str, selected_case: Dict, model: str, active_chat: Dict):
    """统一处理文字输入后的问诊提交。"""
    if not question or not question.strip():
        return

    question = question.strip()
    history = active_chat["history"]

    messages = build_patient_messages(selected_case, history, question)
    patient_answer = call_ollama(messages, model=model, temperature=0.45)

    record = {
        "doctor": question,
        "patient": patient_answer,
        "agent_trace": [
            "读取当前病例角色卡与已完成问诊记录。",
            "判断学生问题对应的症状、病史、风险或中医四诊信息。",
            "仅按病例设定中已经允许暴露的信息组织患者口吻回答。",
            "若学生问到舌象，则匹配并展示当前病例绑定的匿名舌象图。",
        ],
    }

    if asks_tongue(question):
        tongue_images = get_tongue_images(selected_case)
        if tongue_images:
            record["tongue_images"] = tongue_images

    history.append(record)
    active_chat["updated_at"] = datetime.now().strftime("%m-%d %H:%M")

    # 用学生第一个问题自动生成左侧问诊标题。
    if active_chat.get("title") == "新问诊":
        active_chat["title"] = question[:16] + ("..." if len(question) > 16 else "")


def prepare_case_for_prompt(case: Dict) -> Dict:
    """给大模型看的病例信息：去掉图片路径，避免患者回答中说出图片路径。"""
    case_for_prompt = json.loads(json.dumps(case, ensure_ascii=False))

    if "_file" in case_for_prompt:
        del case_for_prompt["_file"]

    tcm_info = case_for_prompt.get("tcm_info", {})
    if "tongue_images" in tcm_info:
        del tcm_info["tongue_images"]
    if "tongue_image_status" in tcm_info:
        del tcm_info["tongue_image_status"]

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
                base_url="https://api.deepseek.com",
            )

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
            )

            return response.choices[0].message.content.strip()

    except Exception as e:
        return f"【DeepSeek API调用失败】请检查API Key、余额、网络或模型名称。错误提示：{e}"

    # 2. 如果没有配置 DeepSeek API Key，则备用调用本地 Ollama
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }

    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception as e:
        return f"【本地模型暂未连接】请确认 Ollama 已启动、模型名称正确。错误提示：{e}"


def build_patient_messages(case: Dict, history: List[Dict], question: str) -> List[Dict]:
    history_text = "\n".join(
        [f"医生：{h['doctor']}\n患者：{h['patient']}" for h in history[-8:]]
    )
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
        {"role": "user", "content": user_prompt},
    ]


def flatten_score_misses(score_result: Dict, limit: int = 8) -> List[str]:
    misses = []
    for dim, value in score_result.items():
        for item in value.get("miss", []):
            misses.append(f"{dim}：{item}")
    return misses[:limit]


def generate_supervisor_hint(case: Dict, history: List[Dict], score_result: Dict) -> str:
    """无需模型也能展示的督导下一步建议。"""
    if not history:
        required = get_case_required_questions(case)
        first_targets = "、".join(required[:4]) if required else "主诉、病程、风险筛查和舌脉信息"
        return f"建议先从开放式主诉开始，再按病例必问点推进。本例优先覆盖：{first_targets}。"

    misses = flatten_score_misses(score_result, limit=5)
    if misses:
        suggestion = "；".join(misses[:3])
        return f"当前最需要补强的是：{suggestion}。下一轮建议用开放式问题补问风险、鉴别诊断或中医四诊中尚未覆盖的部分。"

    return "当前核心问诊覆盖较好。下一步可以请学生做阶段性总结，并进一步追问风险保护因素、既往用药史和家族史。"


def build_supervisor_messages(
    case: Dict,
    history: List[Dict],
    score_result: Dict,
    supervisor_history: List[Dict],
    question: str,
) -> List[Dict]:
    dialogue_text = "\n".join(
        [f"医生：{h['doctor']}\n患者：{h['patient']}" for h in history[-10:]]
    )
    supervisor_text = "\n".join(
        [f"学生：{h['student']}\n督导：{h['supervisor']}" for h in supervisor_history[-6:]]
    )

    score_summary = {
        dim: {
            "score": value.get("score"),
            "weight": value.get("weight"),
            "hit": value.get("hit", []),
            "miss": value.get("miss", []),
        }
        for dim, value in score_result.items()
    }

    system_prompt = f"""
你是神志病中医精神心理方向的教学督导Agent，正在和患者Agent共同支持医学生问诊训练。
你能看到当前病例标准信息、学生与患者的对话、规则评分和病例必问点。

【督导原则】
1. 以教学反馈为主，回答学生关于问诊质量、下一步追问、风险筛查、中医四诊和SOAP书写的问题。
2. 可以参考标准病例信息，但不要一上来把完整诊断、证型和标准答案全部揭示给学生。
3. 优先指出已经覆盖了什么、还缺什么、下一步建议问什么。
4. 遇到自伤自杀、精神病性症状、躁狂/双相线索时，强调继续筛查，但不要提供真实诊疗处置。
5. 回复简洁、具体、可执行，一般控制在180字以内。
6. 本系统仅用于教学训练，不用于真实临床诊疗。

【当前病例】
{json.dumps(prepare_case_for_prompt(case), ensure_ascii=False, indent=2)}

【当前规则评分】
{json.dumps(score_summary, ensure_ascii=False, indent=2)}

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
):
    if not question or not question.strip():
        return

    question = question.strip()
    supervisor_history = active_chat.setdefault("supervisor_history", [])
    messages = build_supervisor_messages(
        selected_case,
        active_chat.get("history", []),
        score_result,
        supervisor_history,
        question,
    )
    answer = call_ollama(messages, model=model, temperature=0.25)
    if "暂未连接" in answer or "调用失败" in answer:
        answer = generate_supervisor_hint(
            selected_case, active_chat.get("history", []), score_result
        ) + "\n\n> 当前模型未连接，以上为规则版督导提示。"

    supervisor_history.append({"student": question, "supervisor": answer})
    active_chat["updated_at"] = datetime.now().strftime("%m-%d %H:%M")



def html_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def score_status(total_score: float) -> str:
    if total_score >= 85:
        return "优秀"
    if total_score >= 70:
        return "较完整"
    if total_score >= 45:
        return "进行中"
    return "待展开"


def top_missing_items(score_result: Dict, limit: int = 4) -> List[str]:
    items = []
    for dim, value in score_result.items():
        for miss in value.get("miss", []):
            items.append(f"{dim}：{miss}")
    return items[:limit]


def render_supervisor_hero():
    st.markdown(
        """
        <div class="supervisor-hero">
            <div class="supervisor-hero-title">双Agent联动督导台</div>
            <div class="supervisor-hero-subtitle">患者Agent负责模拟应答，督导Agent实时评估问诊质量，并给出下一步教学建议。</div>
        </div>
        <div class="agent-flow">
            <div class="agent-flow-step">学生问诊</div>
            <div class="agent-flow-step">患者回应</div>
            <div class="agent-flow-step">督导反馈</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_case_target_panel(selected_case: Dict):
    required_questions = get_case_required_questions(selected_case)
    target_items = required_questions[:7] if required_questions else ["主诉/病程/诱因", "风险筛查", "舌象脉象"]
    target_html = "".join(f"<li>{html_escape(item)}</li>" for item in target_items)

    extracted_info = selected_case.get("extracted_info", {})
    focus_parts = []
    if extracted_info.get("sleep"):
        focus_parts.append(f"睡眠：{extracted_info['sleep']}")
    if extracted_info.get("appetite_gastrointestinal"):
        focus_parts.append(f"食欲胃肠：{extracted_info['appetite_gastrointestinal']}")
    if extracted_info.get("urination_defecation"):
        focus_parts.append(f"二便：{extracted_info['urination_defecation']}")
    focus_text = " ｜ ".join(focus_parts) if focus_parts else "根据学生问诊逐步补充睡眠、饮食二便和风险信息"

    tcm_info = selected_case.get("tcm_info", {})
    st.markdown(
        f"""
        <div class="supervisor-panel">
            <div class="supervisor-panel-title">
                <span>病例训练目标</span>
                <span class="supervisor-panel-kicker">CASE TARGETS</span>
            </div>
            <ul class="target-list">{target_html}</ul>
            <div class="compact-caption">采集重点：{html_escape(focus_text)}</div>
            <div class="compact-caption">四诊重点：舌象 {html_escape(tcm_info.get('tongue', '未填写'))} ｜ 脉象 {html_escape(tcm_info.get('pulse', '未填写'))} ｜ 体质 {html_escape(tcm_info.get('constitution', '未填写'))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_score_panel(score_result: Dict, total_score: float):
    misses = top_missing_items(score_result, limit=4)
    miss_text = "、".join(misses) if misses else "核心维度覆盖较好，可进入阶段性总结。"
    st.markdown(
        f"""
        <div class="supervisor-panel">
            <div class="supervisor-panel-title">
                <span>实时评分</span>
                <span class="supervisor-panel-kicker">LIVE SCORE</span>
            </div>
            <div class="score-dashboard">
                <div class="score-tile">
                    <div class="score-value">{total_score:.1f}</div>
                    <div class="score-label">当前总分 / 100</div>
                </div>
                <div class="score-tile">
                    <div class="score-value">{html_escape(score_status(total_score))}</div>
                    <div class="score-label">问诊覆盖状态</div>
                </div>
            </div>
            <div class="compact-caption">优先补强：{html_escape(miss_text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_next_step_panel(selected_case: Dict, history: List[Dict], score_result: Dict):
    hint = generate_supervisor_hint(selected_case, history, score_result)
    st.markdown(
        f"""
        <div class="supervisor-panel">
            <div class="supervisor-panel-title">
                <span>下一步建议</span>
                <span class="supervisor-panel-kicker">NEXT MOVE</span>
            </div>
            <div class="next-step-box">{html_escape(hint)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def score_dialogue(history: List[Dict], case: Dict = None) -> Tuple[Dict, Dict]:
    """规则评分：稳定、可解释，并接入当前病例的必问点。"""
    doctor_text = " ".join([h["doctor"] for h in history])

    completeness_weight = 20 if case else 25
    communication_weight = 10 if case else 15

    dimensions = {
        "问诊完整性": {
            "weight": completeness_weight,
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
            "weight": communication_weight,
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
            "items": {
                "总结/诊断思路": ["总结", "判断", "考虑", "诊断", "辨证", "下一步"]
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
{json.dumps(prepare_case_for_prompt(case), ensure_ascii=False, indent=2)}

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
inject_custom_css()

cases = load_cases()
if not cases:
    st.error("未找到病例文件。请确认 cases 文件夹中有 JSON 病例。")
    st.stop()

case_options = {
    get_case_title(case): case
    for case in cases
}
default_case_title = list(case_options.keys())[0]

init_chat_sessions(default_case_title)
render_chat_sidebar(default_case_title)

active_chat = get_active_chat()

# 防止某个病例文件被删除、改名后出错。
if active_chat["case_title"] not in case_options:
    active_chat["case_title"] = default_case_title

selected_case = case_options[active_chat["case_title"]]
model = active_chat.get("model", "deepseek-v4-flash")
history = active_chat["history"]
active_chat.setdefault("soap", "")

# 兼容部分原有逻辑。
st.session_state.history = history

left, right = st.columns([2, 1])

with left:
    st.subheader("一、学生问诊区")

    tool_col, info_col = st.columns([1, 5])

    with tool_col:
        # Streamlit 新版本使用 popover；旧版本自动退回 expander。
        if hasattr(st, "popover"):
            settings_panel = st.popover("➕ 设置")
        else:
            settings_panel = st.expander("➕ 设置", expanded=False)

        with settings_panel:
            st.markdown("### 训练设置")

            new_model = st.text_input(
                "大模型名称",
                value=active_chat.get("model", "deepseek-v4-flash"),
                key=f"model_{st.session_state.active_chat_id}",
            )

            st.markdown("#### 病例库筛选")
            syndrome_filter = st.selectbox(
                "按证型筛选",
                options=["全部"] + unique_case_values(cases, get_case_syndrome),
                key="case_filter_syndrome",
            )
            diagnosis_filter = st.selectbox(
                "按诊断大类筛选",
                options=["全部"] + unique_case_values(cases, get_case_diagnosis),
                key="case_filter_diagnosis",
            )
            risk_filter = st.selectbox(
                "按风险等级筛选",
                options=["全部"] + unique_case_values(cases, get_case_risk),
                key="case_filter_risk",
            )

            filtered_cases = filter_cases_by_facets(
                cases, syndrome_filter, diagnosis_filter, risk_filter
            )
            filtered_case_options = {get_case_title(case): case for case in filtered_cases}
            st.caption(f"当前筛选结果：{len(filtered_cases)}/{len(cases)}例")

            new_case_title = active_chat["case_title"]
            if filtered_cases:
                case_titles = list(filtered_case_options.keys())
                current_index = (
                    case_titles.index(active_chat["case_title"])
                    if active_chat["case_title"] in case_titles
                    else 0
                )

                new_case_title = st.selectbox(
                    "选择模拟病例",
                    options=case_titles,
                    index=current_index,
                    key=f"case_{st.session_state.active_chat_id}",
                )

                random_col, apply_col = st.columns(2)
                with random_col:
                    if st.button(
                        "随机抽病例",
                        use_container_width=True,
                        key=f"random_{st.session_state.active_chat_id}",
                    ):
                        reset_chat_for_case(
                            active_chat, random.choice(case_titles), new_model
                        )
                        st.rerun()

                with apply_col:
                    if st.button(
                        "应用并重置",
                        use_container_width=True,
                        key=f"apply_{st.session_state.active_chat_id}",
                    ):
                        reset_chat_for_case(active_chat, new_case_title, new_model)
                        st.rerun()
            else:
                st.warning("当前筛选条件下没有病例，请调整筛选条件。")

            st.caption("切换或随机抽取病例后会重置当前问诊，避免前后病例混杂。")

    with info_col:
        st.markdown(
            f"<div class='current-case-pill'>病例库驱动训练 ｜ 当前病例：{selected_case.get('title', active_chat['case_title'])} ｜ 模型：{model}</div>",
            unsafe_allow_html=True,
        )

    with st.container(height=450, border=True):
        if history:
            for h in history:
                with st.chat_message("user"):
                    st.markdown(h["doctor"])
                with st.chat_message("assistant"):
                    st.markdown(h["patient"])

                    if h.get("agent_trace"):
                        with st.expander("患者Agent响应过程", expanded=False):
                            st.caption("这里展示的是教学用处理步骤，不是模型内部隐藏推理。")
                            for step in h["agent_trace"]:
                                st.markdown(
                                    f"<div class='agent-trace-item'>• {html_escape(step)}</div>",
                                    unsafe_allow_html=True,
                                )

                    if h.get("tongue_images"):
                        for img in h["tongue_images"]:
                            if os.path.exists(img):
                                st.image(img, caption="当前病例舌象参考图", width=260)
                            else:
                                st.warning(f"未找到舌象图片：{img}")
        else:
            st.markdown(
                "<div class='student-chat-empty'>问诊记录会显示在这里。请在下方输入第一句问诊。</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div class='student-composer-label'>学生问诊输入</div>", unsafe_allow_html=True)
    with st.form(key=f"patient_form_{st.session_state.active_chat_id}", clear_on_submit=True):
        input_col, send_col = st.columns([9, 1])
        with input_col:
            patient_question = st.text_input(
                "学生问诊输入",
                placeholder="请输入你的问诊问题，例如：你最近主要哪里不舒服？",
                label_visibility="collapsed",
            )
        with send_col:
            patient_submitted = st.form_submit_button("➤", help="发送问诊", use_container_width=True)

    if patient_submitted:
        if patient_question.strip():
            with st.status("患者Agent正在读取病例角色卡并组织回答...", expanded=False) as status:
                submit_question(patient_question, selected_case, model, active_chat)
                status.update(label="患者Agent已生成回答", state="complete")
            st.rerun()
        else:
            st.warning("请输入问诊问题。")

with right:
    score_result, score_detail = score_dialogue(history, selected_case)
    total_score = sum(v["score"] for v in score_result.values())

    st.markdown("#### 督导老师")
    st.caption("围绕当前病例和问诊记录提问，督导老师会结合评分结果给出教学反馈。")

    with st.form(key=f"supervisor_form_{st.session_state.active_chat_id}"):
        supervisor_input_col, supervisor_send_col = st.columns([8, 1])
        with supervisor_input_col:
            supervisor_question = st.text_input(
                "向督导老师提问",
                placeholder="我还需要问些什么内容",
                label_visibility="collapsed",
            )
        with supervisor_send_col:
            ask_supervisor = st.form_submit_button("➤", help="发送", use_container_width=True)

    if ask_supervisor:
        submit_supervisor_question(
            supervisor_question, selected_case, score_result, model, active_chat
        )
        st.rerun()

    supervisor_history = active_chat.setdefault("supervisor_history", [])
    with st.expander("历史反馈", expanded=False):
        if supervisor_history:
            for item in supervisor_history[-6:]:
                st.markdown(
                    f"<div class='agent-bubble-student'><b>学生：</b>{html_escape(item['student'])}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div class='agent-bubble-supervisor'><b>督导：</b>{html_escape(item['supervisor'])}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("还没有向督导Agent提问。")

    st.divider()

    render_score_panel(score_result, total_score)

    with st.expander("查看各维度评分明细", expanded=False):
        for dim, v in score_result.items():
            st.write(f"**{dim}：{v['score']}/{v['weight']}**")
            st.progress(min(1.0, v["score"] / v["weight"] if v["weight"] else 0))
            if v["miss"]:
                st.caption("待补充：" + "、".join(v["miss"][:3]))

    render_next_step_panel(selected_case, history, score_result)

    render_case_target_panel(selected_case)

    with st.expander("当前病例标准信息与舌象", expanded=False):
        st.write(f"主诉：{selected_case.get('chief_complaint', '未填写')}")
        st.write(f"教学证型：{selected_case.get('tcm_info', {}).get('syndrome', '未填写')}")
        st.write(f"诊断大类：{get_case_diagnosis(selected_case)}")
        st.write(f"风险：{selected_case.get('risk_level', '需进一步评估')}")
        tongue_preview = get_tongue_images(selected_case)
        if tongue_preview:
            for img in tongue_preview:
                st.image(img, caption="舌象参考图", width=220)

st.divider()

tab1, tab2, tab3 = st.tabs(["评分报告", "SOAP病历", "问诊记录导出"])

with tab1:
    st.subheader("四、自动评分报告")
    if st.button("生成评分报告"):
        st.markdown(generate_rule_feedback(score_result))
    else:
        st.info("完成几轮问诊后，点击按钮生成评分报告。")

with tab2:
    st.subheader("五、自动生成SOAP病历")
    if st.button("生成SOAP病历"):
        active_chat["soap"] = generate_soap(history, selected_case, model=model)

    if active_chat.get("soap"):
        st.markdown(active_chat["soap"])
    else:
        st.info("建议至少完成5轮问诊后再生成病历。")

with tab3:
    st.subheader("六、导出问诊记录")
    export_data = {
        "case": selected_case,
        "history": history,
        "score": score_result,
        "supervisor_history": active_chat.get("supervisor_history", []),
        "training_targets": {
            "required_questions": get_case_required_questions(selected_case),
            "risk_level": selected_case.get("risk_level", "需进一步评估"),
            "syndrome": get_case_syndrome(selected_case),
            "diagnosis_category": get_case_diagnosis(selected_case),
        },
    }
    st.download_button(
        "下载JSON记录",
        data=json.dumps(export_data, ensure_ascii=False, indent=2),
        file_name="dialogue_record.json",
        mime="application/json",
    )
