import json
import mimetypes
import os
import unicodedata
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

from scale_assessments import empty_scale_assessments, normalize_scale_assessments
from shenzhi_chat_core import (
    DEFAULT_MODEL,
    build_case_panel_data,
    build_scale_panel_data,
    build_training_review_report,
    evaluate_training_completion,
    generate_soap,
    generate_rule_feedback,
    generate_supervisor_hint,
    get_case_diagnosis,
    get_case_syndrome,
    score_dialogue,
    score_event_summary,
    submit_patient_question,
    submit_supervisor_question,
    update_scale_assessment,
)
import stability_store as store

MODEL_OPTIONS = [
    {"value": DEFAULT_MODEL, "label": "DeepSeek V4 Flash"},
    {"value": "deepseek-chat", "label": "DeepSeek Chat"},
    {"value": "qwen2.5:7b", "label": "Ollama Qwen2.5 7B"},
]


def now_label() -> str:
    return datetime.now().strftime("%m-%d %H:%M")


def load_cases() -> List[Dict]:
    cases = []
    for file in sorted(Path("cases").glob("*.json")):
        with file.open("r", encoding="utf-8") as case_file:
            case = json.load(case_file)
            case["_file"] = str(file)
            cases.append(case)
    return cases


def get_case_title(case: Dict) -> str:
    return case.get("title", case.get("case_id", "未命名病例"))


def default_case_title() -> str:
    cases = load_cases()
    return get_case_title(cases[0]) if cases else "默认病例"


def case_options() -> Dict[str, Dict]:
    return {get_case_title(case): case for case in load_cases()}


def case_option_payload(case: Dict) -> Dict:
    return {
        "title": get_case_title(case),
        "caseId": case.get("case_id", ""),
        "caseCode": case_code(case, {"case_title": get_case_title(case)}),
        "syndrome": get_case_syndrome(case),
        "diagnosis": get_case_diagnosis(case),
    }


def list_workbench_options() -> Dict:
    return {
        "cases": [case_option_payload(case) for case in load_cases()],
        "models": MODEL_OPTIONS,
    }


def selected_case_for_chat(chat: Dict) -> Dict:
    options = case_options()
    if not options:
        return {}

    case_title = chat.get("case_title")
    if case_title in options:
        return options[case_title]

    fallback_title = next(iter(options.keys()))
    chat["case_title"] = fallback_title
    return options[fallback_title]


def case_code(case: Dict, chat: Dict) -> str:
    case_id = str(case.get("case_id") or chat.get("case_title") or "")
    return case_id.replace("case_", "病例") if case_id else "病例"


def tongue_image_payload(image_path: str) -> Dict:
    filename = Path(str(image_path)).name
    return {
        "filename": filename,
        "url": f"/api/tongue-images/{quote(filename)}",
    }


def resolve_tongue_image(filename: str) -> Optional[Path]:
    path = Path("tongue_images") / Path(str(filename)).name
    return path if path.exists() and path.is_file() else None


def default_chat(case_title: str) -> Dict:
    now = now_label()
    return {
        "title": "新问诊",
        "case_title": case_title,
        "model": DEFAULT_MODEL,
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
        "pinned": False,
        "created_at": now,
        "updated_at": now,
    }


def normalize_chat(chat: Dict, fallback_case_title: str) -> Dict:
    normalized = default_chat(fallback_case_title)
    normalized.update(chat or {})
    normalized["scale_assessments"] = normalize_scale_assessments(
        normalized.get("scale_assessments")
    )
    normalized["pinned"] = bool(normalized.get("pinned", False))
    return normalized


def chat_summary(chat_id: str, chat: Dict, active_chat_id: str) -> Dict:
    return {
        "id": chat_id,
        "title": chat.get("title", "新问诊"),
        "caseTitle": chat.get("case_title", ""),
        "time": chat.get("updated_at") or chat.get("created_at", ""),
        "createdAt": chat.get("created_at", ""),
        "updatedAt": chat.get("updated_at", ""),
        "pinned": bool(chat.get("pinned", False)),
        "active": chat_id == active_chat_id,
    }


def messages_from_history(history: List[Dict]) -> List[Dict]:
    messages = []
    for turn_index, record in enumerate(history, start=1):
        doctor = str(record.get("doctor", "")).strip()
        patient = str(record.get("patient", "")).strip()
        if doctor:
            messages.append(
                {
                    "id": f"{turn_index}-doctor",
                    "turn": turn_index,
                    "role": "doctor",
                    "content": doctor,
                }
            )
        if patient:
            patient_message = {
                "id": f"{turn_index}-patient",
                "turn": turn_index,
                "role": "patient",
                "content": patient,
                "tongueImages": [
                    tongue_image_payload(image_path)
                    for image_path in record.get("tongue_images", [])
                ],
            }
            score = score_event_summary(record.get("score_event"))
            if score:
                patient_message["score"] = score
            messages.append(patient_message)
    return messages


def chat_detail_payload(
    chat_id: str,
    chat: Dict,
    active_chat_id: str,
    error: str = "",
) -> Dict:
    selected_case = selected_case_for_chat(chat)
    history = chat.get("history", [])
    score_result, _score_detail = score_dialogue(history, selected_case or None)
    total_score = round(sum(value.get("score", 0) for value in score_result.values()), 1)
    supervisor_history = chat.get("supervisor_history") or []
    completion = evaluate_training_completion(history, selected_case, score_result) if selected_case else {}
    case_panel = build_case_panel_data(selected_case) if selected_case else {}
    case_panel["tongueImages"] = [
        tongue_image_payload(image_path)
        for image_path in case_panel.get("tongueImages", [])
    ]
    payload = {
        "id": chat_id,
        "activeChatId": active_chat_id,
        "title": chat.get("title", "新问诊"),
        "case": {
            "title": get_case_title(selected_case) if selected_case else chat.get("case_title", ""),
            "caseId": selected_case.get("case_id", ""),
            "caseCode": case_code(selected_case, chat),
            "syndrome": get_case_syndrome(selected_case) if selected_case else "未填写",
            "diagnosis": get_case_diagnosis(selected_case) if selected_case else "未填写",
        },
        "model": chat.get("model", DEFAULT_MODEL),
        "turnCount": len(history),
        "messages": messages_from_history(history),
        "score": {
            "total": total_score,
            "dimensions": score_result,
        },
        "supervisor": {
            "history": [
                {
                    "id": f"{index}-{item.get('created_at', '')}",
                    "question": item.get("student", ""),
                    "answer": item.get("supervisor", ""),
                    "createdAt": item.get("created_at", ""),
                }
                for index, item in enumerate(supervisor_history, start=1)
            ],
            "nextStepHint": generate_supervisor_hint(selected_case, history, score_result)
            if selected_case
            else "",
        },
        "review": {
            "completion": completion,
            "scoreSummary": generate_rule_feedback(score_result),
            "report": chat.get("review_report", ""),
            "soap": chat.get("soap", ""),
            "reportGeneratedAt": chat.get("review_report_generated_at", ""),
        },
        "scale": build_scale_panel_data(chat, selected_case, history) if selected_case else {},
        "casePanel": case_panel,
        "pendingPatientRetry": chat.get("pending_patient_retry") or {},
        "requestState": chat.get("request_state") or {},
    }
    if error:
        payload["error"] = error
    return payload


def sort_summaries(items: List[Dict]) -> List[Dict]:
    return sorted(
        items,
        key=lambda item: (
            item.get("pinned", False),
            item.get("updatedAt") or item.get("time") or "",
        ),
        reverse=True,
    )


def ensure_chat_state() -> Tuple[Dict[str, Dict], str]:
    fallback_case = default_case_title()
    sessions = {
        chat_id: normalize_chat(chat, fallback_case)
        for chat_id, chat in store.load_chat_sessions(limit=200).items()
    }

    if not sessions:
        chat_id = str(uuid.uuid4())[:8]
        sessions[chat_id] = default_chat(fallback_case)
        active_chat_id = chat_id
    else:
        restored_active_id = store.load_active_chat_id()
        active_chat_id = (
            restored_active_id
            if restored_active_id in sessions
            else list(sessions.keys())[-1]
        )

    store.save_all_chat_sessions(sessions, active_chat_id)
    return sessions, active_chat_id


def list_chats() -> Dict:
    sessions, active_chat_id = ensure_chat_state()
    summaries = [
        chat_summary(chat_id, chat, active_chat_id)
        for chat_id, chat in sessions.items()
    ]
    return {
        "activeChatId": active_chat_id,
        "chats": sort_summaries(summaries),
    }


def get_chat_detail(chat_id: str) -> Optional[Dict]:
    sessions, active_chat_id = ensure_chat_state()
    chat = sessions.get(chat_id)
    if chat is None:
        return None
    return chat_detail_payload(chat_id, chat, active_chat_id)


def create_chat(payload: Optional[Dict] = None) -> Dict:
    payload = payload or {}
    sessions, _active_chat_id = ensure_chat_state()
    options = case_options()
    requested_case_title = str(payload.get("caseTitle") or "").strip()
    case_title = (
        requested_case_title
        if requested_case_title in options
        else default_case_title()
    )
    model = str(payload.get("model") or "").strip() or DEFAULT_MODEL

    chat_id = str(uuid.uuid4())[:8]
    sessions[chat_id] = default_chat(case_title)
    sessions[chat_id]["model"] = model[:80]
    store.save_all_chat_sessions(sessions, chat_id)
    store.log_event(
        "api_chat_created",
        chat_id=chat_id,
        case_title=case_title,
        model=sessions[chat_id]["model"],
    )
    return list_chats()


def patch_chat(chat_id: str, payload: Dict) -> Optional[Dict]:
    sessions, active_chat_id = ensure_chat_state()
    if chat_id not in sessions:
        return None

    chat = sessions[chat_id]
    if "title" in payload:
        title = str(payload.get("title") or "").strip() or "新问诊"
        chat["title"] = title[:24]
    if "pinned" in payload:
        chat["pinned"] = bool(payload.get("pinned"))
    if payload.get("active") is True:
        active_chat_id = chat_id
    chat["updated_at"] = now_label()
    store.save_all_chat_sessions(sessions, active_chat_id)
    store.log_event("api_chat_updated", chat_id=chat_id)
    return list_chats()


def patch_chat_settings(chat_id: str, payload: Dict) -> Optional[Dict]:
    sessions, active_chat_id = ensure_chat_state()
    if chat_id not in sessions:
        return None

    chat = sessions[chat_id]
    error = ""
    if "caseTitle" in payload:
        requested_case_title = str(payload.get("caseTitle") or "")
        options = case_options()
        if requested_case_title not in options:
            error = "未找到该病例。"
        elif requested_case_title != chat.get("case_title"):
            if chat.get("history"):
                error = "当前会话已有问诊记录，请新建问诊后再切换病例。"
            else:
                chat["case_title"] = requested_case_title
                chat["scale_assessments"] = empty_scale_assessments()
                chat["supervisor_history"] = []
                chat["score_log"] = []
                chat["soap"] = ""
                chat["review_report"] = ""
                chat["review_report_generated_at"] = ""
                chat["pending_patient_retry"] = {}
                chat["request_state"] = {}
                chat["updated_at"] = now_label()
                store.log_event("api_chat_case_changed", chat_id=chat_id, case_title=requested_case_title)

    if "model" in payload:
        model = str(payload.get("model") or "").strip()
        if model:
            chat["model"] = model[:80]
            chat["updated_at"] = now_label()
            store.log_event("api_chat_model_changed", chat_id=chat_id, model=chat["model"])

    store.save_all_chat_sessions(sessions, active_chat_id)
    return chat_detail_payload(chat_id, chat, active_chat_id, error=error)


def submit_chat_message(chat_id: str, payload: Dict) -> Optional[Dict]:
    sessions, _active_chat_id = ensure_chat_state()
    if chat_id not in sessions:
        return None

    active_chat_id = chat_id
    chat = sessions[chat_id]
    selected_case = selected_case_for_chat(chat)

    def save_current_state() -> None:
        store.save_all_chat_sessions(sessions, active_chat_id)

    result = submit_patient_question(
        str(payload.get("question") or ""),
        selected_case,
        chat,
        model=chat.get("model", DEFAULT_MODEL),
        save=save_current_state,
    )
    store.save_all_chat_sessions(sessions, active_chat_id)
    return chat_detail_payload(
        chat_id,
        chat,
        active_chat_id,
        error="" if result.get("ok") else result.get("error", "生成失败"),
    )


def submit_chat_supervisor(chat_id: str, payload: Dict) -> Optional[Dict]:
    sessions, _active_chat_id = ensure_chat_state()
    if chat_id not in sessions:
        return None

    active_chat_id = chat_id
    chat = sessions[chat_id]
    selected_case = selected_case_for_chat(chat)
    score_result, _score_detail = score_dialogue(chat.get("history", []), selected_case or None)

    def save_current_state() -> None:
        store.save_all_chat_sessions(sessions, active_chat_id)

    result = submit_supervisor_question(
        str(payload.get("question") or ""),
        selected_case,
        score_result,
        chat.get("model", DEFAULT_MODEL),
        chat,
        save=save_current_state,
    )
    store.save_all_chat_sessions(sessions, active_chat_id)
    return chat_detail_payload(
        chat_id,
        chat,
        active_chat_id,
        error="" if result.get("ok") else result.get("error", "生成失败"),
    )


def generate_chat_review_report(chat_id: str) -> Optional[Dict]:
    sessions, active_chat_id = ensure_chat_state()
    if chat_id not in sessions:
        return None

    chat = sessions[chat_id]
    selected_case = selected_case_for_chat(chat)
    history = chat.get("history", [])
    score_result, _score_detail = score_dialogue(history, selected_case or None)
    completion = evaluate_training_completion(history, selected_case, score_result)
    chat["review_report"] = build_training_review_report(
        chat,
        selected_case,
        history,
        score_result,
        completion,
    )
    chat["review_report_generated_at"] = now_label()
    chat["updated_at"] = chat["review_report_generated_at"]
    store.save_all_chat_sessions(sessions, active_chat_id)
    store.log_event("api_review_report_generated", chat_id=chat_id)
    return chat_detail_payload(chat_id, chat, active_chat_id)


def generate_chat_soap(chat_id: str) -> Optional[Dict]:
    sessions, active_chat_id = ensure_chat_state()
    if chat_id not in sessions:
        return None

    chat = sessions[chat_id]
    selected_case = selected_case_for_chat(chat)
    history = chat.get("history", [])
    score_result, _score_detail = score_dialogue(history, selected_case or None)
    completion = evaluate_training_completion(history, selected_case, score_result)
    if not completion.get("ready"):
        return chat_detail_payload(
            chat_id,
            chat,
            active_chat_id,
            error="暂不能生成 SOAP，请先补充：" + "、".join(completion.get("missing", [])),
        )

    chat["soap"] = generate_soap(
        history,
        selected_case,
        model=chat.get("model", DEFAULT_MODEL),
        scale_assessments=chat.get("scale_assessments"),
    )
    chat["review_report"] = ""
    chat["review_report_generated_at"] = ""
    chat["updated_at"] = now_label()
    store.save_all_chat_sessions(sessions, active_chat_id)
    store.log_event("api_soap_generated", chat_id=chat_id)
    return chat_detail_payload(chat_id, chat, active_chat_id)


def patch_chat_scale(chat_id: str, payload: Dict) -> Optional[Dict]:
    sessions, active_chat_id = ensure_chat_state()
    if chat_id not in sessions:
        return None

    chat = sessions[chat_id]
    scale_key = str(payload.get("scaleKey") or "")
    answers = payload.get("answers") if isinstance(payload.get("answers"), dict) else {}
    selected_case = selected_case_for_chat(chat)
    try:
        update_scale_assessment(chat, scale_key, answers)
    except ValueError as error:
        return chat_detail_payload(chat_id, chat, active_chat_id, error=str(error))

    store.save_all_chat_sessions(sessions, active_chat_id)
    store.log_event("api_scale_updated", chat_id=chat_id, scale_key=scale_key)
    return chat_detail_payload(chat_id, chat, active_chat_id)


def retry_chat_message(chat_id: str) -> Optional[Dict]:
    sessions, _active_chat_id = ensure_chat_state()
    if chat_id not in sessions:
        return None

    chat = sessions[chat_id]
    pending_retry = chat.get("pending_patient_retry") or {}
    question = pending_retry.get("question", "")
    return submit_chat_message(chat_id, {"question": question})


def dismiss_chat_retry(chat_id: str) -> Optional[Dict]:
    sessions, active_chat_id = ensure_chat_state()
    if chat_id not in sessions:
        return None

    chat = sessions[chat_id]
    chat["pending_patient_retry"] = {}
    chat["request_state"] = {}
    chat["updated_at"] = now_label()
    store.save_all_chat_sessions(sessions, active_chat_id)
    store.log_event("api_chat_retry_dismissed", chat_id=chat_id)
    return chat_detail_payload(chat_id, chat, active_chat_id)


def delete_chat(chat_id: str) -> Optional[Dict]:
    sessions, active_chat_id = ensure_chat_state()
    if chat_id not in sessions:
        return None

    del sessions[chat_id]
    store.delete_chat_session(chat_id)
    if not sessions:
        new_chat_id = str(uuid.uuid4())[:8]
        sessions[new_chat_id] = default_chat(default_case_title())
        active_chat_id = new_chat_id
    elif active_chat_id == chat_id:
        active_chat_id = list(sessions.keys())[-1]

    store.save_all_chat_sessions(sessions, active_chat_id)
    store.log_event("api_chat_deleted", chat_id=chat_id)
    return list_chats()


def export_chat(chat_id: str) -> Optional[Dict]:
    sessions, active_chat_id = ensure_chat_state()
    chat = sessions.get(chat_id)
    if chat is None:
        return None
    return {
        "chat_id": chat_id,
        "active_chat_id": active_chat_id,
        "session": chat,
    }


PDF_PAGE_WIDTH = 595
PDF_PAGE_HEIGHT = 842
PDF_MARGIN_X = 44
PDF_MARGIN_Y = 48


def _pdf_text_hex(text: str) -> str:
    return str(text).encode("utf-16-be", errors="replace").hex().upper()


def _text_units(text: str) -> float:
    units = 0.0
    for char in str(text):
        if char == "\t":
            units += 2
        elif ord(char) < 128:
            units += 0.55
        elif unicodedata.east_asian_width(char) in {"F", "W", "A"}:
            units += 1.0
        else:
            units += 0.8
    return units


def _wrap_pdf_text(text: str, max_units: float) -> List[str]:
    lines: List[str] = []
    for paragraph in str(text).replace("\r\n", "\n").split("\n"):
        if not paragraph:
            lines.append("")
            continue

        current = ""
        current_units = 0.0
        for char in paragraph:
            char_units = _text_units(char)
            if current and current_units + char_units > max_units:
                lines.append(current)
                current = char
                current_units = char_units
            else:
                current += char
                current_units += char_units
        if current:
            lines.append(current)
    return lines


def _pdf_style(style: str) -> Tuple[int, float, str]:
    styles = {
        "title": (18, 1.45, "0 0.45 0.40 rg"),
        "section": (13, 1.55, "0.12 0.18 0.28 rg"),
        "meta": (10, 1.45, "0.34 0.39 0.47 rg"),
        "doctor": (11, 1.55, "0.04 0.46 0.42 rg"),
        "patient": (11, 1.55, "0.86 0.35 0.03 rg"),
        "score": (10, 1.45, "0.38 0.42 0.50 rg"),
        "body": (11, 1.55, "0.12 0.18 0.28 rg"),
        "small": (9, 1.45, "0.48 0.53 0.60 rg"),
    }
    return styles.get(style, styles["body"])


def _role_label(role: str) -> str:
    return "医生" if role == "doctor" else "患者"


def _format_score_lines(score: Optional[Dict]) -> List[str]:
    if not score:
        return []
    lines = []
    if score.get("gained"):
        lines.append(f"本轮新增得分：{score.get('gained')}")
    if score.get("newCoverage"):
        lines.append(f"新增覆盖：{score.get('newCoverage')}")
    if score.get("stillNeeded"):
        lines.append(f"仍需补问：{score.get('stillNeeded')}")
    return lines


def _export_pdf_lines(chat_id: str, chat: Dict, active_chat_id: str) -> List[Tuple[str, str]]:
    detail = chat_detail_payload(chat_id, chat, active_chat_id)
    case = detail.get("case", {})
    lines: List[Tuple[str, str]] = [
        ("title", "神志病科 AI 问诊记录"),
        ("meta", f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
        ("meta", f"问诊编号：{chat_id}"),
        ("meta", f"问诊标题：{detail.get('title') or '新问诊'}"),
        ("meta", f"当前病例：{case.get('caseCode', '')} · {case.get('syndrome', '')}"),
        ("meta", f"诊断信息：{case.get('diagnosis', '未填写')}"),
        ("meta", f"模型：{detail.get('model', DEFAULT_MODEL)}"),
        ("meta", f"问诊轮次：{detail.get('turnCount', 0)} 轮"),
        ("body", ""),
        ("section", "一、医患问诊记录"),
    ]

    messages = detail.get("messages") or []
    if not messages:
        lines.append(("small", "暂无问诊记录。"))
    else:
        for message in messages:
            role = str(message.get("role", ""))
            turn = message.get("turn", "")
            content = str(message.get("content") or "").strip()
            prefix = f"第 {turn} 轮 · {_role_label(role)}："
            lines.append(("doctor" if role == "doctor" else "patient", prefix))
            lines.append(("body", content or "（无内容）"))
            for score_line in _format_score_lines(message.get("score")):
                lines.append(("score", score_line))
            tongue_images = message.get("tongueImages") or []
            if tongue_images:
                image_names = "、".join(str(item.get("filename", "")) for item in tongue_images)
                lines.append(("small", f"舌象图片：{image_names}"))
            lines.append(("body", ""))

    supervisor = detail.get("supervisor", {})
    feedbacks = supervisor.get("history") or []
    lines.extend([("section", "二、督导反馈记录")])
    if not feedbacks:
        lines.append(("small", "暂无督导反馈记录。"))
    else:
        for index, feedback in enumerate(feedbacks, start=1):
            created_at = feedback.get("createdAt") or ""
            lines.append(("body", f"{index}. 学生提问：{feedback.get('question', '')}"))
            lines.append(("score", f"督导反馈：{feedback.get('answer', '')}"))
            if created_at:
                lines.append(("small", f"反馈时间：{created_at}"))
            lines.append(("body", ""))

    return lines


def build_chat_record_pdf(chat_id: str, chat: Dict, active_chat_id: str) -> bytes:
    source_lines = _export_pdf_lines(chat_id, chat, active_chat_id)
    pages: List[List[Tuple[str, str, float]]] = [[]]
    y = float(PDF_PAGE_HEIGHT - PDF_MARGIN_Y)

    for style, text in source_lines:
        font_size, line_ratio, _color = _pdf_style(style)
        line_height = font_size * line_ratio
        max_units = (PDF_PAGE_WIDTH - PDF_MARGIN_X * 2) / font_size
        wrapped = _wrap_pdf_text(text, max_units)
        if not wrapped:
            wrapped = [""]
        for line in wrapped:
            if y < PDF_MARGIN_Y + line_height:
                pages.append([])
                y = float(PDF_PAGE_HEIGHT - PDF_MARGIN_Y)
            pages[-1].append((style, line, y))
            y -= line_height

    font_id = 3
    cid_font_id = 4
    descriptor_id = 5
    page_ids: List[int] = []
    content_ids: List[int] = []
    next_object_id = 6
    for _page in pages:
        page_ids.append(next_object_id)
        content_ids.append(next_object_id + 1)
        next_object_id += 2

    max_object_id = next_object_id - 1
    objects: List[bytes] = [b""] * (max_object_id + 1)
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    objects[font_id] = (
        b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light "
        b"/Encoding /UniGB-UCS2-H /DescendantFonts [4 0 R] >>"
    )
    objects[cid_font_id] = (
        b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 5 >> "
        b"/FontDescriptor 5 0 R /DW 1000 >>"
    )
    objects[descriptor_id] = (
        b"<< /Type /FontDescriptor /FontName /STSong-Light /Flags 6 "
        b"/FontBBox [-260 -160 1000 1000] /ItalicAngle 0 "
        b"/Ascent 880 /Descent -120 /CapHeight 880 /StemV 80 >>"
    )

    for index, page in enumerate(pages):
        content_parts: List[str] = []
        for style, line, line_y in page:
            font_size, _line_ratio, color = _pdf_style(style)
            x = PDF_MARGIN_X + (10 if style in {"score", "small"} else 0)
            text_hex = _pdf_text_hex(line)
            content_parts.append(
                f"BT\n{color}\n/F1 {font_size} Tf\n1 0 0 1 {x:.1f} {line_y:.1f} Tm\n<{text_hex}> Tj\nET"
            )
        content = "\n".join(content_parts).encode("ascii")
        content_id = content_ids[index]
        page_id = page_ids[index]
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PDF_PAGE_WIDTH} {PDF_PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = (
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii")
            + content
            + b"\nendstream"
        )

    pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = [0] * (max_object_id + 1)
    for object_id in range(1, max_object_id + 1):
        offsets[object_id] = len(pdf)
        pdf += f"{object_id} 0 obj\n".encode("ascii") + objects[object_id] + b"\nendobj\n"

    xref_offset = len(pdf)
    pdf += f"xref\n0 {max_object_id + 1}\n".encode("ascii")
    pdf += b"0000000000 65535 f \n"
    for object_id in range(1, max_object_id + 1):
        pdf += f"{offsets[object_id]:010d} 00000 n \n".encode("ascii")
    pdf += (
        f"trailer\n<< /Size {max_object_id + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    return pdf


def export_chat_pdf(chat_id: str) -> Optional[Tuple[bytes, str]]:
    sessions, active_chat_id = ensure_chat_state()
    chat = sessions.get(chat_id)
    if chat is None:
        return None
    detail = chat_detail_payload(chat_id, chat, active_chat_id)
    case_code_label = detail.get("case", {}).get("caseCode") or "病例"
    title = str(detail.get("title") or "问诊记录").strip() or "问诊记录"
    safe_title = "".join(char if char.isalnum() or char in "-_." else "_" for char in title)[:32]
    filename = f"{case_code_label}_{safe_title}_{chat_id}_问诊记录.pdf"
    return build_chat_record_pdf(chat_id, chat, active_chat_id), filename


class ApiHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._write_headers()
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json({"status": "ok"})
            return
        if path == "/api/workbench-options":
            self._json(list_workbench_options())
            return
        filename = self._match_tongue_image(path)
        if filename:
            self._serve_tongue_image(filename)
            return
        if path == "/api/chats":
            self._json(list_chats())
            return
        chat_id = self._match_chat_export(path)
        if chat_id:
            payload = export_chat_pdf(chat_id)
            self._pdf_or_not_found(payload)
            return
        chat_id = self._match_chat_id(path)
        if chat_id:
            self._json_or_not_found(get_chat_detail(chat_id))
            return
        self._not_found()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/chats":
            self._json(create_chat(self._read_json()), status=HTTPStatus.CREATED)
            return
        chat_id = self._match_chat_child(path, "messages")
        if chat_id:
            self._json_or_not_found(submit_chat_message(chat_id, self._read_json()))
            return
        chat_id = self._match_chat_child(path, "supervisor")
        if chat_id:
            self._json_or_not_found(submit_chat_supervisor(chat_id, self._read_json()))
            return
        chat_id = self._match_chat_child(path, "review-report")
        if chat_id:
            self._json_or_not_found(generate_chat_review_report(chat_id))
            return
        chat_id = self._match_chat_child(path, "soap")
        if chat_id:
            self._json_or_not_found(generate_chat_soap(chat_id))
            return
        chat_id = self._match_chat_child(path, "retry")
        if chat_id:
            self._json_or_not_found(retry_chat_message(chat_id))
            return
        self._not_found()

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        chat_id = self._match_chat_child(path, "scales")
        if chat_id:
            self._json_or_not_found(patch_chat_scale(chat_id, self._read_json()))
            return
        chat_id = self._match_chat_child(path, "settings")
        if chat_id:
            self._json_or_not_found(patch_chat_settings(chat_id, self._read_json()))
            return
        chat_id = self._match_chat_id(path)
        if chat_id:
            self._json_or_not_found(patch_chat(chat_id, self._read_json()))
            return
        self._not_found()

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        chat_id = self._match_chat_child(path, "retry")
        if chat_id:
            self._json_or_not_found(dismiss_chat_retry(chat_id))
            return
        chat_id = self._match_chat_id(path)
        if chat_id:
            self._json_or_not_found(delete_chat(chat_id))
            return
        self._not_found()

    def _match_chat_id(self, path: str) -> Optional[str]:
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "chats"]:
            return parts[2]
        return None

    def _match_chat_export(self, path: str) -> Optional[str]:
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "chats"] and parts[3] == "export":
            return parts[2]
        return None

    def _match_chat_child(self, path: str, child: str) -> Optional[str]:
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "chats"] and parts[3] == child:
            return parts[2]
        return None

    def _match_tongue_image(self, path: str) -> Optional[str]:
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "tongue-images"]:
            return Path(unquote(parts[2])).name
        return None

    def _read_json(self) -> Dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {}

    def _write_headers(self, content_type: str = "application/json") -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, payload: Dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self._write_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json_or_not_found(self, payload: Optional[Dict]) -> None:
        if payload is None:
            self._not_found()
        else:
            self._json(payload)

    def _pdf_or_not_found(self, payload: Optional[Tuple[bytes, str]]) -> None:
        if payload is None:
            self._not_found()
            return

        data, filename = payload
        fallback = "shenzhi_dialogue_record.pdf"
        self.send_response(HTTPStatus.OK)
        self._write_headers(content_type="application/pdf")
        self.send_header(
            "Content-Disposition",
            f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}",
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _not_found(self) -> None:
        self._json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def _serve_tongue_image(self, filename: str) -> None:
        path = resolve_tongue_image(filename)
        if path is None:
            self._not_found()
            return

        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self._write_headers(content_type=content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def resolve_server_host() -> str:
    return os.getenv("SHENZHI_API_HOST") or ("0.0.0.0" if os.getenv("PORT") else "127.0.0.1")


def resolve_server_port() -> int:
    return int(os.getenv("PORT") or os.getenv("SHENZHI_API_PORT", "8765"))


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), ApiHandler)
    print(f"Shenzhi API listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run(host=resolve_server_host(), port=resolve_server_port())
