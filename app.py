import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import requests
import streamlit as st
from openai import OpenAI
from scale_assessments import (
    CLINICIAN_SCALE_CONFIG,
    HAMD17_ITEMS,
    HAMA14_ITEMS,
    HAMA_SCORE_OPTIONS,
    build_scale_summary,
    clinician_scale_evidence,
    empty_scale_assessments,
    hama_partial_total,
    hama_progress,
    hama_total,
    hamd17_partial_total,
    hamd17_progress,
    hamd17_total,
    normalize_scale_assessments,
    recommended_scale_plan,
    scale_summary_markdown,
    timestamp_now,
)
from stability_diagnostics import run_health_check
from stability_store import (
    delete_chat_session,
    ensure_periodic_backup,
    load_active_chat_id,
    load_chat_sessions,
    log_event,
    save_all_chat_sessions,
)

APP_TITLE = "神志思训"
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_REQUEST_TIMEOUT = 25
MODEL_MAX_ATTEMPTS = 3
CHAT_RENDER_BATCH_SIZE = 16

st.set_page_config(page_title="神志思训", layout="wide")


class ModelCallError(RuntimeError):
    """模型服务不可用时抛出，避免将错误文本写入患者对话。"""


def persist_chat_sessions() -> None:
    """Best-effort persistence: storage failures should not crash the training UI."""
    chat_sessions = st.session_state.get("chat_sessions", {})
    active_chat_id = st.session_state.get("active_chat_id", "")
    serialized_sessions = json.dumps(
        {"active_chat_id": active_chat_id, "chat_sessions": chat_sessions},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    if st.session_state.get("_persisted_sessions_snapshot") == serialized_sessions:
        return
    try:
        save_all_chat_sessions(chat_sessions, active_chat_id)
        st.session_state["_persisted_sessions_snapshot"] = serialized_sessions
    except Exception as error:
        try:
            log_event("session_save_failed", error=str(error))
        except Exception:
            pass


def reset_visible_turns(chat_id: str) -> None:
    st.session_state.setdefault("chat_visible_turns", {})[chat_id] = CHAT_RENDER_BATCH_SIZE


def ensure_startup_maintenance() -> None:
    """Run lightweight maintenance once per browser session."""
    if st.session_state.get("_startup_maintenance_done"):
        return
    try:
        backup_path = ensure_periodic_backup()
        st.session_state["_startup_backup_path"] = str(backup_path or "")
    except Exception as error:
        log_event("database_backup_failed", error=str(error))
        st.session_state["_startup_backup_path"] = ""
    try:
        st.session_state["_startup_health_report"] = run_health_check()
    except Exception as error:
        log_event("startup_health_check_failed", error=str(error))
        st.session_state["_startup_health_report"] = {
            "summary": {"status": "fail", "label": "自检失败", "pass": 0, "warn": 0, "fail": 1},
            "checks": [
                {
                    "name": "系统自检",
                    "status": "fail",
                    "message": f"无法完成自检：{error}",
                }
            ],
        }
    st.session_state["_startup_maintenance_done"] = True


def inject_custom_css():
    """Figma export driven UI shell: Sidebar + ChatArea + ScorePanel."""
    st.markdown(
        """
        <style>
        :root {
            --sz-bg: #f5f7fa;
            --sz-sidebar: #1a2332;
            --sz-sidebar-2: #243044;
            --sz-surface: #ffffff;
            --sz-ink: #1f2937;
            --sz-muted: #6b7280;
            --sz-soft: #f3f4f6;
            --sz-line: #e5e7eb;
            --sz-line-strong: #d1d5db;
            --sz-teal: #14b8a6;
            --sz-teal-dark: #0d9488;
            --sz-orange: #fb923c;
            --sz-danger: #f87171;
            --sz-sidebar-width: 14rem;
            --sz-score-width: 18rem;
            --sz-radius: 0.75rem;
        }

        #MainMenu,
        footer,
        header,
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="stHeader"] {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
        }

        html,
        body,
        .stApp,
        [data-testid="stAppViewContainer"] {
            margin: 0 !important;
            background: var(--sz-bg) !important;
            color: var(--sz-ink) !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif !important;
            overflow: hidden !important;
        }

        [data-testid="stAppViewBlockContainer"] {
            max-width: none !important;
            padding: 0 !important;
        }

        .block-container {
            max-width: none !important;
            padding: 0 !important;
        }

        div[data-testid="stVerticalBlock"] {
            gap: 0 !important;
        }

        [data-testid="stSidebar"] {
            width: var(--sz-sidebar-width) !important;
            min-width: var(--sz-sidebar-width) !important;
            max-width: var(--sz-sidebar-width) !important;
            background: var(--sz-sidebar) !important;
            border-right: 0 !important;
            color: #fff !important;
        }

        [data-testid="stSidebar"] > div:first-child {
            width: var(--sz-sidebar-width) !important;
            padding: 1.25rem 1rem 0.75rem !important;
            background: var(--sz-sidebar) !important;
        }

        .figma-brand {
            display: flex;
            align-items: center;
            gap: 0.625rem;
            margin-bottom: 1.25rem;
            user-select: none;
        }

        .figma-brand-icon {
            width: 2rem;
            height: 2rem;
            flex: 0 0 2rem;
        }

        .figma-brand-wordmark {
            display: flex;
            flex-direction: column;
            line-height: 1;
        }

        .figma-brand-title {
            color: #fff;
            font-size: 0.9375rem;
            font-weight: 700;
            letter-spacing: 0.08em;
        }

        .figma-brand-subtitle {
            margin-top: 0.125rem;
            color: #5eead4;
            font-size: 0.5rem;
            font-weight: 400;
            letter-spacing: 0.18em;
        }

        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            width: 100% !important;
            min-height: 2.5rem !important;
            justify-content: flex-start !important;
            gap: 0.5rem !important;
            padding: 0.5rem 0.75rem !important;
            border: 0 !important;
            border-radius: 0.5rem !important;
            background: var(--sz-teal) !important;
            color: #fff !important;
            font-size: 0.875rem !important;
            font-weight: 650 !important;
            box-shadow: none !important;
            transition: background 0.16s ease !important;
        }

        [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
            background: var(--sz-teal-dark) !important;
        }

        [data-testid="stSidebar"] .stButton > button:not([kind="primary"]) {
            width: 100% !important;
            min-height: 2.25rem !important;
            justify-content: flex-start !important;
            padding: 0.5rem !important;
            border: 0 !important;
            border-radius: 0.5rem !important;
            background: transparent !important;
            color: #e5e7eb !important;
            font-size: 0.75rem !important;
            font-weight: 500 !important;
            text-align: left !important;
            box-shadow: none !important;
        }

        [data-testid="stSidebar"] .stButton > button:not([kind="primary"]):hover {
            background: rgba(255, 255, 255, 0.10) !important;
            color: #fff !important;
        }

        [data-testid="stSidebar"] input {
            height: 2.15rem !important;
            min-height: 2.15rem !important;
            padding: 0 0.65rem !important;
            border: 1px solid rgba(255, 255, 255, 0.10) !important;
            border-radius: 0.5rem !important;
            background: rgba(255, 255, 255, 0.06) !important;
            color: #e5e7eb !important;
            font-size: 0.75rem !important;
            box-shadow: none !important;
        }

        [data-testid="stSidebar"] input::placeholder {
            color: #9ca3af !important;
        }

        .figma-sidebar-label {
            margin: 1.25rem 0 0.5rem;
            padding: 0 0.25rem;
            color: #9ca3af;
            font-size: 0.75rem;
            line-height: 1.25;
        }

        .sidebar-meta,
        .figma-session-meta {
            margin: -0.2rem 0 0.35rem 0.5rem !important;
            color: #6b7280 !important;
            font-size: 0.625rem !important;
            line-height: 1.2 !important;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        [data-testid="stSidebar"] button[data-testid="stPopoverButton"] {
            width: 2rem !important;
            min-width: 2rem !important;
            height: 2rem !important;
            min-height: 2rem !important;
            padding: 0 !important;
            border: 0 !important;
            border-radius: 0.5rem !important;
            background: transparent !important;
            color: #9ca3af !important;
            font-size: 1rem !important;
            box-shadow: none !important;
        }

        [data-testid="stSidebar"] button[data-testid="stPopoverButton"]:hover {
            background: rgba(255, 255, 255, 0.10) !important;
            color: #fff !important;
        }

        .figma-sidebar-account {
            margin-top: 1.25rem;
            padding-top: 0.75rem;
            border-top: 1px solid rgba(255, 255, 255, 0.10);
        }

        .figma-user-row {
            display: flex;
            align-items: center;
            gap: 0.625rem;
            min-height: 2.5rem;
            padding: 0.5rem;
            border-radius: 0.5rem;
            color: #d1d5db;
            font-size: 0.75rem;
        }

        .figma-user-avatar {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 1.75rem;
            height: 1.75rem;
            border-radius: 999px;
            background: var(--sz-teal);
            color: #fff;
            font-weight: 700;
        }

        .figma-shell div[data-testid="stHorizontalBlock"] {
            gap: 0 !important;
        }

        div[data-testid="column"]:has([class*="st-key-figma_chat_area_"]) {
            min-width: 0 !important;
        }

        div[data-testid="column"]:has([class*="st-key-figma_score_panel_"]) {
            flex: 0 0 var(--sz-score-width) !important;
            width: var(--sz-score-width) !important;
            min-width: var(--sz-score-width) !important;
            max-width: var(--sz-score-width) !important;
        }

        [class*="st-key-figma_chat_area_"] {
            height: 100vh !important;
            min-height: 100vh !important;
            background: var(--sz-bg) !important;
            overflow: hidden !important;
        }

        .figma-chat-header {
            height: 4.1rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            padding: 0.75rem 1.25rem;
            border-bottom: 1px solid var(--sz-line);
            background: #fff;
        }

        .figma-header-left {
            min-width: 0;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .figma-workspace-title {
            color: #1f2937;
            font-size: 0.875rem;
            font-weight: 700;
            white-space: nowrap;
        }

        .figma-tag-row {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            min-width: 0;
            overflow: hidden;
        }

        .figma-tag {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            height: 1.7rem;
            padding: 0 0.75rem;
            border: 1px solid var(--sz-line);
            border-radius: 999px;
            background: #fff;
            color: #4b5563;
            font-size: 0.75rem;
            white-space: nowrap;
        }

        .figma-tag strong {
            color: var(--sz-teal-dark);
            font-weight: 700;
        }

        .figma-header-actions {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 0.5rem;
        }

        .figma-round-select {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            height: 1.8rem;
            padding: 0 0.5rem;
            border-radius: 0.25rem;
            background: #f3f4f6;
            color: #374151;
            font-size: 0.75rem;
            font-weight: 600;
        }

        [class*="st-key-figma_chat_scroll_"] {
            height: calc(100vh - 8.8rem) !important;
            min-height: calc(100vh - 8.8rem) !important;
            padding: 1rem 1.25rem 1.25rem !important;
            border: 0 !important;
            background: var(--sz-bg) !important;
            overflow-y: auto !important;
        }

        [class*="st-key-figma_chat_scroll_"] > div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 0 !important;
            background: transparent !important;
        }

        .figma-empty-state {
            height: calc(100vh - 12rem);
            display: flex;
            align-items: center;
            justify-content: center;
            color: #9ca3af;
            font-size: 0.875rem;
        }

        .figma-message-row {
            display: flex;
            gap: 0.75rem;
            margin-bottom: 1rem;
        }

        .figma-message-row.doctor {
            flex-direction: row-reverse;
        }

        .figma-avatar {
            width: 2rem;
            height: 2rem;
            flex: 0 0 2rem;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            color: #fff;
            font-size: 0.75rem;
            font-weight: 800;
        }

        .figma-avatar.patient { background: var(--sz-orange); }
        .figma-avatar.doctor { background: var(--sz-teal); }

        .figma-message-stack {
            max-width: 65%;
            display: flex;
            flex-direction: column;
            align-items: flex-start;
        }

        .figma-message-row.doctor .figma-message-stack {
            align-items: flex-end;
        }

        .figma-bubble {
            padding: 0.625rem 1rem;
            border-radius: 1rem;
            color: #1f2937;
            background: #fff;
            font-size: 0.875rem;
            line-height: 1.7;
            box-shadow: 0 1px 4px rgba(15, 23, 42, 0.06);
        }

        .figma-bubble.patient {
            border-top-left-radius: 0;
        }

        .figma-bubble.doctor {
            border-top-right-radius: 0;
            background: var(--sz-teal);
            color: #fff;
            box-shadow: none;
        }

        .figma-message-meta {
            margin-bottom: 0.25rem;
            color: #9ca3af;
            font-size: 0.6875rem;
            line-height: 1.2;
        }

        .figma-score-toggle {
            margin-top: 0.375rem;
            color: var(--sz-teal-dark);
            font-size: 0.6875rem;
        }

        [class*="st-key-figma_chat_scroll_"] div[data-testid="stExpander"] {
            width: 18rem !important;
            margin: 0.375rem 0 0 !important;
            border: 1px solid var(--sz-line) !important;
            border-radius: 0.75rem !important;
            background: #f9fafb !important;
            box-shadow: none !important;
            overflow: hidden !important;
        }

        [class*="st-key-figma_chat_scroll_"] div[data-testid="stExpander"] summary {
            min-height: 2.2rem !important;
            padding: 0 0.75rem !important;
            color: #4b5563 !important;
            font-size: 0.75rem !important;
            font-weight: 600 !important;
        }

        .turn-score-summary {
            color: #1f2937;
            font-size: 0.75rem;
            font-weight: 700;
            line-height: 1.5;
        }

        .turn-score-summary span,
        .turn-score-detail b {
            color: var(--sz-teal-dark);
        }

        .turn-score-detail {
            margin-top: 0.3rem;
            color: #6b7280;
            font-size: 0.6875rem;
            line-height: 1.55;
        }

        [class*="st-key-figma_composer_"] {
            height: 4.7rem !important;
            padding: 0.75rem 1rem !important;
            border-top: 1px solid var(--sz-line) !important;
            background: #fff !important;
        }

        [class*="st-key-figma_composer_"] > div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 0 !important;
            background: transparent !important;
        }

        [class*="st-key-figma_composer_"] div[data-testid="stHorizontalBlock"] {
            min-height: 3.05rem !important;
            align-items: center !important;
            gap: 0.5rem !important;
            padding: 0.5rem 0.75rem !important;
            border: 1px solid var(--sz-line) !important;
            border-radius: 0.75rem !important;
            background: #f9fafb !important;
        }

        [class*="st-key-figma_composer_"] div[data-testid="stForm"] {
            width: 100% !important;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
        }

        [class*="st-key-figma_composer_"] input {
            height: 2.2rem !important;
            min-height: 2.2rem !important;
            border: 0 !important;
            background: transparent !important;
            color: #1f2937 !important;
            font-size: 0.875rem !important;
            box-shadow: none !important;
        }

        [class*="st-key-figma_composer_"] input::placeholder {
            color: #9ca3af !important;
        }

        .figma-mic-button {
            width: 2rem !important;
            height: 2rem !important;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 0.5rem !important;
            background: transparent !important;
            color: #9ca3af !important;
            font-size: 1rem;
        }

        [class*="st-key-figma_composer_"] div[data-testid="stFormSubmitButton"] > button {
            width: 2rem !important;
            min-width: 2rem !important;
            height: 2rem !important;
            min-height: 2rem !important;
            padding: 0 !important;
            border: 0 !important;
            border-radius: 0.5rem !important;
            background: var(--sz-teal) !important;
            color: #fff !important;
            font-size: 0.875rem !important;
            box-shadow: none !important;
        }

        [class*="st-key-figma_score_panel_"] {
            height: 100vh !important;
            min-height: 100vh !important;
            overflow-y: auto !important;
            border-left: 1px solid var(--sz-line) !important;
            background: #fff !important;
        }

        [class*="st-key-figma_score_panel_"] > div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 0 !important;
            background: #fff !important;
        }

        .score-dashboard {
            margin: 0 !important;
        }

        .score-tile {
            min-height: 7.75rem;
            margin: 1rem 1rem 0.75rem;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            border: 1px solid var(--sz-line);
            border-radius: 0.75rem;
            background: linear-gradient(180deg, #f0fdfa 0%, #f7fbfb 100%);
        }

        .score-value {
            color: var(--sz-teal-dark);
            font-size: 2rem;
            line-height: 1;
            font-weight: 900;
        }

        .score-label {
            margin-top: 0.55rem;
            color: #374151;
            font-size: 0.875rem;
            font-weight: 650;
        }

        [class*="st-key-figma_score_panel_"] [data-baseweb="tab-list"] {
            height: 2.75rem !important;
            border-bottom: 1px solid var(--sz-line) !important;
            padding: 0 !important;
            gap: 0 !important;
        }

        [class*="st-key-figma_score_panel_"] [data-baseweb="tab"] {
            flex: 1 1 0 !important;
            min-width: 0 !important;
            height: 2.75rem !important;
            min-height: 2.75rem !important;
            padding: 0 !important;
            color: #6b7280 !important;
            font-size: 0.6875rem !important;
            font-weight: 650 !important;
            white-space: nowrap !important;
        }

        [class*="st-key-figma_score_panel_"] [data-baseweb="tab"][aria-selected="true"] {
            color: var(--sz-teal-dark) !important;
        }

        [class*="st-key-figma_score_panel_"] [data-baseweb="tab-highlight"] {
            height: 2px !important;
            background: var(--sz-teal) !important;
        }

        [class*="st-key-figma_score_panel_"] [data-testid="stCaptionContainer"] {
            padding: 1rem 1rem 0 !important;
            color: #9ca3af !important;
            font-size: 0.75rem !important;
            line-height: 1.6 !important;
        }

        [class*="st-key-figma_score_panel_"] div[data-testid="stForm"] {
            margin: 0.75rem 1rem 1rem !important;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
        }

        [class*="st-key-figma_score_panel_"] div[data-testid="stForm"] div[data-testid="stHorizontalBlock"] {
            align-items: center !important;
            gap: 0.5rem !important;
        }

        [class*="st-key-figma_score_panel_"] div[data-testid="stForm"] input {
            height: 2.5rem !important;
            min-height: 2.5rem !important;
            padding: 0 0.75rem !important;
            border: 1px solid var(--sz-line) !important;
            border-radius: 0.5rem !important;
            background: #fff !important;
            color: #374151 !important;
            font-size: 0.875rem !important;
            box-shadow: none !important;
        }

        [class*="st-key-figma_score_panel_"] div[data-testid="stFormSubmitButton"] > button {
            width: 2.5rem !important;
            min-width: 2.5rem !important;
            height: 2.5rem !important;
            min-height: 2.5rem !important;
            padding: 0 !important;
            border: 0 !important;
            border-radius: 0.5rem !important;
            background: #1f2937 !important;
            color: #fff !important;
            box-shadow: none !important;
        }

        [class*="st-key-figma_score_panel_"] div[data-testid="stExpander"] {
            margin: 0 1rem 1rem !important;
            border: 1px solid var(--sz-line) !important;
            border-radius: 0.75rem !important;
            background: #fff !important;
            box-shadow: none !important;
            overflow: hidden !important;
        }

        [class*="st-key-figma_score_panel_"] div[data-testid="stExpander"] summary {
            min-height: 2.75rem !important;
            padding: 0 1rem !important;
            color: #374151 !important;
            font-size: 0.75rem !important;
            font-weight: 650 !important;
            background: #fff !important;
        }

        [class*="st-key-figma_score_panel_"] div[data-testid="stExpanderDetails"] {
            padding: 0.75rem 1rem 1rem !important;
        }

        .next-step-box {
            padding: 0.75rem;
            border: 1px solid #fde68a;
            border-radius: 0.5rem;
            background: #fffbeb;
            color: #4b5563;
            font-size: 0.75rem;
            line-height: 1.65;
        }

        .agent-bubble-student,
        .agent-bubble-supervisor,
        .submit-status-box,
        .review-placeholder {
            padding: 0.75rem;
            border-radius: 0.5rem;
            background: #f9fafb;
            color: #4b5563;
            font-size: 0.75rem;
            line-height: 1.65;
        }

        .agent-bubble-supervisor {
            margin-top: 0.5rem;
            border: 1px solid #fde68a;
            background: #fffbeb;
        }

        .compact-caption,
        .feedback-page-indicator {
            color: #9ca3af;
            font-size: 0.6875rem;
        }

        .dimension-score-list {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .dimension-score-heading {
            display: flex;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.35rem;
        }

        .dimension-score-name,
        .dimension-score-number {
            color: #374151;
            font-size: 0.75rem;
            font-weight: 700;
        }

        .dimension-score-number {
            color: var(--sz-teal-dark);
        }

        .dimension-score-track {
            height: 0.375rem;
            overflow: hidden;
            border-radius: 999px;
            background: #f3f4f6;
        }

        .dimension-score-fill {
            height: 100%;
            border-radius: 999px;
            background: var(--sz-teal);
        }

        .dimension-score-missing {
            margin-top: 0.35rem;
            color: #9ca3af;
            font-size: 0.625rem;
            line-height: 1.4;
        }

        .case-target-section {
            margin-bottom: 1rem;
        }

        .case-target-label {
            margin-bottom: 0.5rem;
            color: #9ca3af;
            font-size: 0.6875rem;
        }

        .case-target-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.5rem 0.75rem;
        }

        .case-target-item {
            display: flex;
            align-items: flex-start;
            gap: 0.375rem;
            color: #4b5563;
            font-size: 0.6875rem;
            line-height: 1.35;
        }

        .case-target-index {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 1rem;
            height: 1rem;
            flex: 0 0 1rem;
            border-radius: 999px;
            background: var(--sz-teal);
            color: #fff;
            font-size: 0.5625rem;
            font-weight: 800;
        }

        .case-target-row {
            display: flex;
            gap: 0.5rem;
            color: #4b5563;
            font-size: 0.6875rem;
            line-height: 1.5;
        }

        .case-target-row-label {
            width: 4rem;
            flex: 0 0 4rem;
            color: #6b7280;
        }

        @media (max-width: 1080px) {
            :root {
                --sz-sidebar-width: 12.5rem;
                --sz-score-width: 17rem;
            }
            .figma-workspace-title { display: none; }
            .figma-tag { padding: 0 0.55rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
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


def get_case_required_questions(case: Dict) -> List[str]:
    questions = case.get("teaching_info", {}).get("required_questions", [])
    return questions if isinstance(questions, list) else []


def required_question_keywords(item: str) -> List[str]:
    keyword_map = {
        "主诉/病程/诱因": ["哪里不舒服", "主要", "不舒服", "症状", "困扰", "多久", "多长时间", "什么时候", "诱因", "原因", "压力", "发生什么", "刺激"],
        "睡眠/食欲/二便": ["睡眠", "失眠", "入睡", "早醒", "多梦", "食欲", "胃口", "大便", "小便", "二便", "饮食"],
        "自伤自杀风险": ["自杀", "轻生", "不想活", "活着没意思", "伤害自己", "自伤", "结束生命", "割腕", "跳楼", "吃药", "死亡", "具体计划", "保护因素"],
        "幻听妄想": [
            "幻听", "幻觉", "妄想", "听到声音", "别人听不到的声音",
            "听到别人听不到", "看见别人看不到", "有人害", "有人要害",
            "有人想害", "有人监视", "有人议论", "有人伤害你", "被害",
            "被监视", "被议论", "被控制", "别人议论", "有人跟踪",
            "怀疑别人",
        ],
        "躁狂或轻躁狂": ["躁狂", "轻躁狂", "兴奋", "话多", "精力", "精力旺盛", "睡得少也不困", "睡得少", "不用睡", "花钱", "冲动消费", "特别自信", "想法很多", "脑子转得快", "活动增多", "易怒"],
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


# ---------------- 多问诊会话管理 ----------------
def normalize_chat_session(chat: Dict, default_case_title: str) -> Dict:
    """补齐旧会话字段，并将意外中断的请求转为可重试状态。"""
    now = datetime.now().strftime("%m-%d %H:%M")
    defaults = {
        "title": "新问诊",
        "case_title": default_case_title,
        "model": st.session_state.get("default_model", "deepseek-v4-flash"),
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
        "created_at": now,
        "updated_at": now,
    }
    for key, value in defaults.items():
        chat.setdefault(key, value)
    chat["scale_assessments"] = normalize_scale_assessments(chat.get("scale_assessments"))

    request_state = chat.get("request_state") or {}
    if request_state.get("status") == "running" and request_state.get("kind") == "patient":
        question = request_state.get("question", "")
        if question:
            chat["pending_patient_retry"] = {
                "question": question,
                "error": "上一次生成可能因页面中断未完成，可以重新生成。",
                "created_at": request_state.get("created_at", now),
            }
        chat["request_state"] = {}
    return chat


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
        "created_at": now,
        "updated_at": now,
    }

    st.session_state.active_chat_id = chat_id
    reset_visible_turns(chat_id)
    persist_chat_sessions()
    log_event("chat_created", chat_id=chat_id, case_title=default_case_title)


def init_chat_sessions(default_case_title: str):
    """初始化问诊会话。"""
    if "default_model" not in st.session_state:
        st.session_state.default_model = "deepseek-v4-flash"

    st.session_state.setdefault("chat_visible_turns", {})

    if "chat_sessions" not in st.session_state:
        restored_sessions = load_chat_sessions()
        st.session_state.chat_sessions = {
            chat_id: normalize_chat_session(chat, default_case_title)
            for chat_id, chat in restored_sessions.items()
        }
        if restored_sessions:
            log_event("sessions_restored", count=len(restored_sessions))
        else:
            create_new_chat(default_case_title)

    if "active_chat_id" not in st.session_state:
        restored_active_id = load_active_chat_id()
        if restored_active_id in st.session_state.chat_sessions:
            st.session_state.active_chat_id = restored_active_id
        else:
            st.session_state.active_chat_id = list(st.session_state.chat_sessions.keys())[-1]

    st.session_state.chat_visible_turns.setdefault(
        st.session_state.active_chat_id, CHAT_RENDER_BATCH_SIZE
    )
    persist_chat_sessions()


def get_active_chat() -> Dict:
    """获取当前正在进行的问诊会话。"""
    return st.session_state.chat_sessions[st.session_state.active_chat_id]


@st.fragment
def render_sidebar_chat_list():
    """搜索历史问诊时只重跑侧栏列表，避免刷新整个工作台。"""
    st.markdown("<div class='figma-sidebar-label'>历史问诊记录</div>", unsafe_allow_html=True)
    chat_items = list(st.session_state.chat_sessions.items())[::-1]
    chat_items.sort(key=lambda item: bool(item[1].get("pinned")), reverse=True)

    if not chat_items:
        st.caption("暂无问诊记录。")

    with st.container(height=360, border=False, key="sidebar_chat_list"):
        for chat_id, chat in chat_items:
            title = chat.get("title", "新问诊")
            case_title = chat.get("case_title", "")
            updated_at = chat.get("updated_at") or chat.get("created_at", "")

            item_col, menu_col = st.columns([0.82, 0.18], gap="small", vertical_alignment="center")
            with item_col:
                if st.button(
                    title,
                    key=f"open_chat_{chat_id}",
                    use_container_width=True,
                ):
                    st.session_state.active_chat_id = chat_id
                    st.session_state.chat_visible_turns.setdefault(
                        chat_id, CHAT_RENDER_BATCH_SIZE
                    )
                    persist_chat_sessions()
                    log_event("chat_opened", chat_id=chat_id)
                    st.rerun()
            with menu_col:
                if hasattr(st, "popover"):
                    session_menu = st.popover("⋮", help="问诊菜单", use_container_width=True)
                else:
                    session_menu = st.expander("⋮", expanded=False)
                with session_menu:
                    st.download_button(
                        "导出问诊记录",
                        data=json.dumps(
                            {"chat_id": chat_id, "session": chat},
                            ensure_ascii=False,
                            indent=2,
                            default=str,
                        ),
                        file_name=f"{chat_id}_dialogue_record.json",
                        mime="application/json",
                        key=f"sidebar_download_{chat_id}",
                        use_container_width=True,
                    )
                    if st.button(
                        "取消固定" if chat.get("pinned") else "固定",
                        key=f"sidebar_pin_{chat_id}",
                        use_container_width=True,
                    ):
                        chat["pinned"] = not bool(chat.get("pinned"))
                        chat["updated_at"] = datetime.now().strftime("%m-%d %H:%M")
                        persist_chat_sessions()
                        st.rerun()
                    rename_title = st.text_input(
                        "重命名",
                        value=title,
                        key=f"sidebar_rename_{chat_id}",
                    )
                    if st.button("保存名称", key=f"sidebar_save_rename_{chat_id}", use_container_width=True):
                        chat["title"] = (rename_title.strip() or "新问诊")[:24]
                        chat["updated_at"] = datetime.now().strftime("%m-%d %H:%M")
                        persist_chat_sessions()
                        log_event("chat_renamed", chat_id=chat_id)
                        st.rerun()
                    if st.button("删除", key=f"sidebar_delete_{chat_id}", use_container_width=True):
                        if len(st.session_state.chat_sessions) > 1:
                            del st.session_state.chat_sessions[chat_id]
                            if st.session_state.active_chat_id == chat_id:
                                st.session_state.active_chat_id = next(iter(st.session_state.chat_sessions.keys()))
                            delete_chat_session(chat_id)
                            persist_chat_sessions()
                            log_event("chat_deleted", chat_id=chat_id)
                            st.rerun()
                        else:
                            st.warning("至少保留一个问诊会话。")
            st.markdown(
                f"<div class='figma-session-meta'>{html_escape(case_title)} · {html_escape(updated_at)}</div>",
                unsafe_allow_html=True,
            )


def figma_brand_logo_html() -> str:
    """Inline the Figma-exported logo mark so the dark sidebar matches the design code."""
    return """
    <div class="figma-brand">
        <svg class="figma-brand-icon" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="logoGradFigma" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stop-color="#2dd4bf" />
                    <stop offset="100%" stop-color="#0d9488" />
                </linearGradient>
            </defs>
            <path d="M16 2L28.124 9V23L16 30L3.876 23V9L16 2Z" fill="url(#logoGradFigma)" />
            <ellipse cx="16" cy="13.5" rx="5.5" ry="6" fill="rgba(255,255,255,0.25)" />
            <circle cx="16" cy="13" r="3.5" fill="none" stroke="white" stroke-width="1.2" stroke-opacity="0.9" />
            <line x1="16" y1="9.5" x2="16" y2="7" stroke="white" stroke-width="1" stroke-opacity="0.7" stroke-linecap="round" />
            <line x1="19.3" y1="11" x2="21.5" y2="9.5" stroke="white" stroke-width="1" stroke-opacity="0.7" stroke-linecap="round" />
            <line x1="19.3" y1="15" x2="21.5" y2="16.5" stroke="white" stroke-width="1" stroke-opacity="0.7" stroke-linecap="round" />
            <line x1="12.7" y1="11" x2="10.5" y2="9.5" stroke="white" stroke-width="1" stroke-opacity="0.7" stroke-linecap="round" />
            <line x1="12.7" y1="15" x2="10.5" y2="16.5" stroke="white" stroke-width="1" stroke-opacity="0.7" stroke-linecap="round" />
            <circle cx="16" cy="7" r="1.2" fill="white" fill-opacity="0.9" />
            <circle cx="21.5" cy="9.5" r="1.2" fill="white" fill-opacity="0.9" />
            <circle cx="21.5" cy="16.5" r="1.2" fill="white" fill-opacity="0.9" />
            <circle cx="10.5" cy="9.5" r="1.2" fill="white" fill-opacity="0.9" />
            <circle cx="10.5" cy="16.5" r="1.2" fill="white" fill-opacity="0.9" />
            <rect x="14.2" y="18.8" width="3.6" height="3" rx="1.8" fill="white" fill-opacity="0.7" />
            <rect x="10" y="22.5" width="12" height="2" rx="1" fill="white" fill-opacity="0.5" />
        </svg>
        <div class="figma-brand-wordmark">
            <span class="figma-brand-title">神志思训</span>
            <span class="figma-brand-subtitle">AI · MIND · TRAINING</span>
        </div>
    </div>
    """


def render_chat_sidebar(default_case_title: str, active_chat: Dict = None, cases: List[Dict] = None):
    """Figma Sidebar：深色品牌区、创建问诊、历史记录、账号入口。"""
    with st.sidebar:
        st.markdown(figma_brand_logo_html(), unsafe_allow_html=True)

        if st.button("+ 新建问诊", type="primary", use_container_width=True):
            create_new_chat(default_case_title)
            st.rerun()

        render_sidebar_chat_list()

        st.markdown(
            """
            <div class="figma-sidebar-account">
                <div class="figma-user-row">
                    <span class="figma-user-avatar">管</span>
                    <span>超级管理员</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def asks_tongue(question: str) -> bool:
    """判断医生是否问到了舌象相关内容。"""
    keywords = ["舌", "舌象", "舌苔", "舌质"]
    return any(k in question for k in keywords)


@st.cache_data(show_spinner=False, ttl=60, max_entries=512)
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


def dialogue_text_from_history(history: List[Dict]) -> Tuple[str, str, str]:
    doctor_text = " ".join([str(h.get("doctor", "")) for h in history])
    patient_text = " ".join([str(h.get("patient", "")) for h in history])
    return doctor_text, patient_text, f"{doctor_text} {patient_text}"


def keyword_matches(text: str, keywords: List[str]) -> List[str]:
    """返回命中的关键词，保留证据给学生看。"""
    text = str(text or "")
    return [keyword for keyword in keywords if keyword and keyword in text]


def find_question_evidence(history: List[Dict], keywords: List[str]) -> Dict:
    """按问诊回合寻找某个评分条目的第一条医生提问证据。"""
    for index, item in enumerate(history, start=1):
        question = str(item.get("doctor", ""))
        matches = keyword_matches(question, keywords)
        if matches:
            return {
                "turn": index,
                "question": question,
                "patient_answer": str(item.get("patient", "")),
                "matched": matches[:4],
                "source": "doctor_question",
            }
    return {}


def risk_denial_evidence(history: List[Dict]) -> Dict:
    """识别患者已明确否认自杀/轻生或具体计划的情况，避免机械追问。"""
    suicide_question_keywords = [
        "自杀", "轻生", "不想活", "活着没意思", "结束生命", "想过死", "想死",
        "伤害自己", "自伤", "自残", "寻死", "想不开",
    ]
    suicide_denial_keywords = [
        "没有自杀", "没想过自杀", "没有轻生", "没想过轻生", "没有不想活",
        "没有想过死", "没有想死", "不想死", "不会去死", "没有伤害自己",
        "没想过伤害自己", "没有自伤", "没有自残",
    ]
    plan_denial_keywords = [
        "没有具体计划", "没具体计划", "没有计划", "没计划", "没有准备",
        "没准备", "不会去做", "不会真的做", "没有方法", "没想好怎么做",
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


def build_score_event(
    before_score: Dict,
    after_score: Dict,
    question: str,
    patient_answer: str,
    turn_index: int,
) -> Dict:
    """记录每一轮问诊带来的可解释评分变化。"""
    new_hits = []
    score_delta = 0.0

    for dim, after_value in after_score.items():
        before_value = before_score.get(dim, {})
        before_hits = set(before_value.get("hit", []))
        after_hits = set(after_value.get("hit", []))
        item_scores = after_value.get("item_scores", {})
        evidence = after_value.get("evidence", {})
        covered_by_denial = set(after_value.get("covered_by_denial", []))
        for item in sorted(after_hits - before_hits):
            new_hits.append({
                "dimension": dim,
                "item": item,
                "score": item_scores.get(item, 0),
                "evidence": evidence.get(item, {}),
                "covered_by_denial": item in covered_by_denial,
            })
        dim_delta = float(after_value.get("score", 0) or 0) - float(before_value.get("score", 0) or 0)
        score_delta += dim_delta

    hit_dimensions = []
    for hit in new_hits:
        if hit["dimension"] not in hit_dimensions:
            hit_dimensions.append(hit["dimension"])
    related_missing = []
    for dim in hit_dimensions:
        for item in after_score.get(dim, {}).get("miss", []):
            related_missing.append(f"{dim}：{item}")

    return {
        "turn": turn_index,
        "question": question,
        "patient_answer": patient_answer,
        "score_delta": round(score_delta, 1),
        "new_hits": new_hits,
        "related_missing": related_missing[:4],
        "next_missing": top_missing_items(after_score, limit=3),
        "created_at": datetime.now().strftime("%m-%d %H:%M"),
    }


def render_turn_score_event(event: Dict):
    new_hits = event.get("new_hits", [])
    if new_hits:
        hit_text = "、".join(
            [f"{hit['dimension']} +{hit.get('score', 0):.1f}：{hit['item']}" for hit in new_hits[:5]]
        )
    else:
        hit_text = "本轮暂未新增评分点。"

    missing = event.get("related_missing") or event.get("next_missing", [])
    missing_text = "、".join(missing[:3]) if missing else "核心评分点覆盖较好。"
    st.markdown(
        f"""
        <div class="turn-score-summary">本轮新增得分：{event.get('score_delta', 0):+.1f} 分</div>
        <div class="turn-score-detail">新增覆盖：{html_escape(hit_text)}</div>
        <div class="turn-score-detail">仍需补问：{html_escape(missing_text)}</div>
        """,
        unsafe_allow_html=True,
    )


def submit_question(question: str, selected_case: Dict, model: str, active_chat: Dict) -> bool:
    """统一处理文字输入后的问诊提交。"""
    if not question or not question.strip():
        return False

    question = question.strip()
    history = active_chat["history"]
    before_score, _ = score_dialogue(history, selected_case)

    messages = build_patient_messages(selected_case, history, question)
    active_chat["request_state"] = {
        "kind": "patient",
        "status": "running",
        "question": question,
        "created_at": datetime.now().strftime("%m-%d %H:%M"),
    }
    persist_chat_sessions()
    try:
        patient_answer = call_ollama(messages, model=model, temperature=0.45)
    except ModelCallError as error:
        active_chat["request_state"] = {}
        active_chat["pending_patient_retry"] = {
            "question": question,
            "error": str(error),
            "created_at": datetime.now().strftime("%m-%d %H:%M"),
        }
        persist_chat_sessions()
        log_event("patient_generation_failed", model=model, error=str(error))
        return False

    record = {
        "doctor": question,
        "patient": patient_answer,
    }

    if asks_tongue(question):
        tongue_images = get_tongue_images(selected_case)
        if tongue_images:
            record["tongue_images"] = tongue_images

    history.append(record)
    after_score, _ = score_dialogue(history, selected_case)
    score_event = build_score_event(before_score, after_score, question, patient_answer, len(history))
    record["score_event"] = score_event
    active_chat.setdefault("score_log", []).append(score_event)

    # 新增问诊后，原先的提交状态和SOAP需要重新确认。
    active_chat["training_submitted"] = False
    active_chat["submitted_at"] = ""
    active_chat["completion_snapshot"] = {}
    active_chat["soap"] = ""
    active_chat["review_report"] = ""
    active_chat["review_report_generated_at"] = ""
    active_chat["request_state"] = {}
    active_chat["pending_patient_retry"] = {}
    active_chat["updated_at"] = datetime.now().strftime("%m-%d %H:%M")

    # 用学生第一个问题自动生成左侧问诊标题。
    if active_chat.get("title") == "新问诊":
        active_chat["title"] = question[:16] + ("..." if len(question) > 16 else "")
    reset_visible_turns(st.session_state.get("active_chat_id", ""))
    persist_chat_sessions()
    log_event("patient_generation_succeeded", model=model, turn=len(history))
    return True


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


@st.cache_resource(show_spinner=False)
def get_deepseek_client(api_key: str) -> OpenAI:
    """复用 HTTP 连接，减少每轮问诊重新初始化客户端的开销。"""
    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=MODEL_REQUEST_TIMEOUT,
        max_retries=0,
    )


def call_ollama(messages: List[Dict], model: str, temperature: float = 0.4) -> str:
    """
    在线版大模型调用：
    优先调用 DeepSeek API。
    如果没有配置 API Key，则保留原来的 Ollama 本地调用作为备用。
    """
    model_stub = (
        os.getenv("SHENZHI_MODEL_STUB", "").strip().lower()
        if os.getenv("SHENZHI_ENABLE_TEST_STUB") == "1"
        else ""
    )
    if model_stub:
        log_event("model_stub_used", mode=model_stub, model=model)
        if model_stub == "success":
            return os.getenv(
                "SHENZHI_MODEL_STUB_RESPONSE",
                "（测试患者回答）最近心情有些低落，睡眠也不太好。",
            )
        if model_stub == "failure":
            raise ModelCallError("测试环境模拟模型暂时不可用。")
        raise ModelCallError(f"未知的测试模型模式：{model_stub}")

    api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
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
                response = get_deepseek_client(api_key).chat.completions.create(
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

            log_event(
                "model_request_succeeded",
                provider=provider,
                model=model,
                attempt=attempt,
                elapsed_ms=round((time.monotonic() - started_at) * 1000),
            )
            return answer
        except Exception as error:
            last_error = str(error)
            log_event(
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
    """无需模型也能展示的督导下一步建议。"""
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
    scale_assessments: Dict = None,
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
            "covered_by_denial": value.get("covered_by_denial", []),
        }
        for dim, value in score_result.items()
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
        active_chat.get("scale_assessments"),
    )
    try:
        answer = call_ollama(messages, model=model, temperature=0.25)
    except ModelCallError as error:
        answer = generate_supervisor_hint(
            selected_case, active_chat.get("history", []), score_result
        ) + "\n\n> 当前模型未连接，以上为规则版督导提示。"
        log_event("supervisor_generation_fallback", model=model, error=str(error))

    supervisor_history.append({
        "student": question,
        "supervisor": answer,
        "created_at": datetime.now().strftime("%m-%d %H:%M"),
    })
    active_chat["show_supervisor_history"] = True
    active_chat["open_supervisor_history_once"] = True
    active_chat["supervisor_history_revision"] = active_chat.get("supervisor_history_revision", 0) + 1
    active_chat["supervisor_feedback_page"] = 0
    active_chat["updated_at"] = datetime.now().strftime("%m-%d %H:%M")
    persist_chat_sessions()



def html_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def top_missing_items(score_result: Dict, limit: int = 4) -> List[str]:
    items = []
    for dim, value in score_result.items():
        for miss in value.get("miss", []):
            items.append(f"{dim}：{miss}")
    return items[:limit]

def render_case_target_panel(selected_case: Dict):
    required_questions = get_case_required_questions(selected_case)
    target_items = required_questions[:7] if required_questions else ["主诉/病程/诱因", "风险筛查", "舌象脉象"]
    target_html = "".join(
        f"""
        <div class="case-target-item">
            <span class="case-target-index">{index}</span>
            <span>{html_escape(item)}</span>
        </div>
        """
        for index, item in enumerate(target_items, start=1)
    )

    extracted_info = selected_case.get("extracted_info", {})
    focus_rows = [
        ("睡眠", extracted_info.get("sleep", "根据问诊逐步补充")),
        ("食欲胃肠", extracted_info.get("appetite_gastrointestinal", "根据问诊逐步补充")),
        ("二便", extracted_info.get("urination_defecation", "根据问诊逐步补充")),
    ]
    tcm_info = selected_case.get("tcm_info", {})
    tcm_rows = [
        ("舌象", tcm_info.get("tongue", "未填写")),
        ("脉象", tcm_info.get("pulse", "未填写")),
        ("体质", tcm_info.get("constitution", "未填写")),
    ]
    focus_html = "".join(
        f"""
        <div class="case-target-row">
            <span class="case-target-row-label">{html_escape(label)}</span>
            <span>{html_escape(value)}</span>
        </div>
        """
        for label, value in focus_rows
    )
    tcm_html = "".join(
        f"""
        <div class="case-target-row">
            <span class="case-target-row-label">{html_escape(label)}</span>
            <span>{html_escape(value)}</span>
        </div>
        """
        for label, value in tcm_rows
    )
    st.markdown(
        f"""
        <div class="case-target-section">
            <div class="case-target-label">病例必问点</div>
            <div class="case-target-grid">{target_html}</div>
        </div>
        <div class="case-target-section">
            <div class="case-target-label">采集重点</div>
            <div class="case-target-rows">{focus_html}</div>
        </div>
        <div class="case-target-section">
            <div class="case-target-label">四诊重点</div>
            <div class="case-target-rows">{tcm_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_score_panel(score_result: Dict, total_score: float):
    st.markdown(
        f"""
        <div class="score-dashboard score-dashboard-single">
            <div class="score-tile">
                <div class="score-value">{total_score:.1f}</div>
                <div class="score-label">当前总分 / 100</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_score_detail_panel(score_result: Dict) -> None:
    items = []
    for dimension, value in score_result.items():
        weight = float(value.get("weight", 0) or 0)
        score = float(value.get("score", 0) or 0)
        percent = min(100.0, max(0.0, score / weight * 100 if weight else 0.0))
        missing = value.get("miss", [])
        missing_html = (
            f"<div class='dimension-score-missing'>待补充：{html_escape('、'.join(missing[:3]))}</div>"
            if missing
            else ""
        )
        items.append(
            "".join(
                [
                    '<div class="dimension-score-item">',
                    '<div class="dimension-score-heading">',
                    f'<span class="dimension-score-name">{html_escape(dimension)}</span>',
                    f'<span class="dimension-score-number">{score:.1f} / {weight:.0f}</span>',
                    "</div>",
                    '<div class="dimension-score-track">',
                    f'<div class="dimension-score-fill" style="width: {percent:.1f}%"></div>',
                    "</div>",
                    missing_html,
                    "</div>",
                ]
            )
        )
    st.markdown(
        f"<div class='dimension-score-list'>{''.join(items)}</div>",
        unsafe_allow_html=True,
    )


def render_next_step_panel(selected_case: Dict, history: List[Dict], score_result: Dict):
    hint = generate_supervisor_hint(selected_case, history, score_result)
    st.markdown(
        f"""
        <div class="next-step-box">{html_escape(hint)}</div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False, max_entries=512)
def evaluate_training_completion(history: List[Dict], selected_case: Dict, score_result: Dict) -> Dict:
    total_score = round(sum(v["score"] for v in score_result.values()), 1)
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
        required_ratio = len(required.get("hit", [])) / max(1, len(required.get("hit", [])) + len(required.get("miss", [])))
        if required_ratio < 0.5:
            missing.append("病例必问点覆盖率建议达到50%以上")

    return {
        "ready": len(missing) == 0,
        "status": "可提交" if not missing else "继续问诊",
        "missing": missing[:6],
        "total_score": total_score,
        "turn_count": len(history),
        "required_ratio": required_ratio,
    }


def invalidate_generated_outputs_after_scale_update(active_chat: Dict) -> None:
    """量表变更后清理旧报告和 SOAP，避免复盘引用过期数据。"""
    active_chat["soap"] = ""
    active_chat["review_report"] = ""
    active_chat["review_report_generated_at"] = ""
    active_chat["updated_at"] = datetime.now().strftime("%m-%d %H:%M")
    persist_chat_sessions()


def render_hamd17_panel(active_chat: Dict, selected_case: Dict, history: List[Dict]) -> None:
    assessments = active_chat["scale_assessments"]
    hamd17 = assessments["hamd17"]
    reference_score = selected_case.get("scale_scores", {}).get("HAMD-24")
    evidence = clinician_scale_evidence(history, "hamd17")
    st.caption("由学生根据问诊和观察逐项评分。17项全部记录后，系统自动计算 HAMD-17 总分。")

    if hamd17.get("status") == "not_started":
        if st.button(
            "开始 HAMD-17 教学评分",
            use_container_width=True,
            key=f"start_hamd17_{st.session_state.active_chat_id}",
        ):
            hamd17["status"] = "in_progress"
            invalidate_generated_outputs_after_scale_update(active_chat)
            st.rerun()
        if reference_score not in (None, ""):
            st.caption(
                f"病例库现存 HAMD-24 历史参考：{reference_score} 分。"
                "量表版本不同，不与本轮 HAMD-17 直接比较。"
            )
        return

    current_answers = hamd17.get("answers", {})
    pending_answers = {}
    with st.form(key=f"hamd17_form_{st.session_state.active_chat_id}"):
        for index, item in enumerate(HAMD17_ITEMS, start=1):
            score_to_option = {
                score: option
                for option, score in item["options"].items()
                if score is not None
            }
            option_labels = list(item["options"].keys())
            current_option = score_to_option.get(current_answers.get(item["key"]), "未记录")
            selected_option = st.selectbox(
                f"{index}. {item['label']}",
                option_labels,
                index=option_labels.index(current_option),
                key=f"hamd17_item_{st.session_state.active_chat_id}_{item['key']}",
            )
            pending_answers[item["key"]] = item["options"][selected_option]
        save_hamd17 = st.form_submit_button("保存 HAMD-17 教学评分", use_container_width=True)

    if save_hamd17:
        hamd17["answers"] = pending_answers
        total = hamd17_total(pending_answers)
        hamd17["status"] = "completed" if total is not None else "in_progress"
        hamd17["completed_at"] = timestamp_now() if total is not None else ""
        invalidate_generated_outputs_after_scale_update(active_chat)
        st.rerun()

    total = hamd17_total(current_answers)
    progress = hamd17_progress(current_answers)
    if total is None:
        st.info(
            f"已记录 {progress}/{len(HAMD17_ITEMS)} 项，当前小计 "
            f"{hamd17_partial_total(current_answers)} 分。完成全部条目后生成正式总分。"
        )
    else:
        st.metric("HAMD-17 本轮教学评分", f"{total} 分")
        if current_answers.get("suicide", 0) > 0:
            st.warning("“自杀”条目评分不为0：教学中应继续补问自杀意念、具体计划、可及手段与保护因素。")

    st.write(f"当前问诊证据覆盖：**{evidence['covered_count']}/{evidence['total_count']} 项**")
    if evidence["covered"]:
        st.caption("已有依据：" + "、".join(evidence["covered"]))
    if evidence["missing"]:
        st.caption("建议补问：" + "、".join(evidence["missing"]))
    if reference_score not in (None, ""):
        st.caption(
            f"病例库现存 HAMD-24 历史参考：{reference_score} 分。"
            "量表版本不同，不与本轮 HAMD-17 直接比较。"
        )


def render_hama_panel(active_chat: Dict, selected_case: Dict, history: List[Dict]) -> None:
    assessments = active_chat["scale_assessments"]
    hama = assessments["hama"]
    evidence = clinician_scale_evidence(history, "hama")
    reference_score = selected_case.get("scale_scores", {}).get("HAMA")
    st.caption("由学生根据问诊和观察逐项评分。14项全部记录后，系统自动计算 HAMA 总分。")

    if hama.get("status") == "not_started":
        if st.button(
            "开始 HAMA 教学评分",
            use_container_width=True,
            key=f"start_hama_{st.session_state.active_chat_id}",
        ):
            hama["status"] = "in_progress"
            invalidate_generated_outputs_after_scale_update(active_chat)
            st.rerun()
    else:
        current_answers = hama.get("answers", {})
        score_to_option = {
            score: option
            for option, score in HAMA_SCORE_OPTIONS.items()
            if score is not None
        }
        option_labels = list(HAMA_SCORE_OPTIONS.keys())
        pending_answers = {}
        with st.form(key=f"hama_form_{st.session_state.active_chat_id}"):
            for index, item in enumerate(HAMA14_ITEMS, start=1):
                current_option = score_to_option.get(current_answers.get(item["key"]), "未记录")
                selected_option = st.selectbox(
                    f"{index}. {item['label']}｜{item['description']}",
                    option_labels,
                    index=option_labels.index(current_option),
                    key=f"hama_item_{st.session_state.active_chat_id}_{item['key']}",
                )
                pending_answers[item["key"]] = HAMA_SCORE_OPTIONS[selected_option]
            save_hama = st.form_submit_button(
                "保存 HAMA 教学评分",
                use_container_width=True,
            )
        if save_hama:
            hama["answers"] = pending_answers
            total = hama_total(pending_answers)
            hama["status"] = "completed" if total is not None else "in_progress"
            hama["completed_at"] = timestamp_now() if total is not None else ""
            invalidate_generated_outputs_after_scale_update(active_chat)
            st.rerun()

    current_answers = hama.get("answers", {})
    total = hama_total(current_answers)
    progress = hama_progress(current_answers)
    if total is None and hama.get("status") != "not_started":
        st.info(
            f"已记录 {progress}/{len(HAMA14_ITEMS)} 项，当前小计 "
            f"{hama_partial_total(current_answers)} 分。完成全部条目后生成正式总分。"
        )
    elif total is not None:
        st.metric("HAMA 本轮教学评分", f"{total} 分")

    st.write(f"当前问诊证据覆盖：**{evidence['covered_count']}/{evidence['total_count']} 项**")
    if evidence["covered"]:
        st.caption("已有依据：" + "、".join(evidence["covered"]))
    if evidence["missing"]:
        st.caption("建议补问：" + "、".join(evidence["missing"]))
    if reference_score not in (None, ""):
        st.caption(f"病例库教学参考：{reference_score} 分。仅用于复盘对照。")


def render_scale_assessment_panel(active_chat: Dict, selected_case: Dict, history: List[Dict]) -> None:
    active_chat["scale_assessments"] = normalize_scale_assessments(
        active_chat.get("scale_assessments")
    )
    scale_plan = recommended_scale_plan(selected_case)
    st.caption("量表记录与100分问诊评分相互独立。以下为按证型和当前病例线索生成的教学推荐。")
    for index, item in enumerate(scale_plan):
        label = CLINICIAN_SCALE_CONFIG[item["key"]]["label"]
        st.info(f"{item['priority']}：{label}。{item['reason']}")
        with st.expander(f"{label} 教学评分", expanded=index == 0):
            if item["key"] == "hamd17":
                render_hamd17_panel(active_chat, selected_case, history)
            else:
                render_hama_panel(active_chat, selected_case, history)


@st.cache_data(show_spinner=False, max_entries=512)
def score_dialogue(history: List[Dict], case: Dict = None) -> Tuple[Dict, Dict]:
    """规则评分：逐条归因、保留证据，并接入当前病例的必问点。"""
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
                    "冲动行为",
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
    for dim, cfg in dimensions.items():
        hit = []
        miss = []
        evidence = {}
        item_scores = {}
        covered_by_denial = []
        item_score = round(cfg["weight"] / max(1, len(cfg["items"])), 1)

        for item, kws in cfg["items"].items():
            item_evidence = find_question_evidence(history, kws)
            if dim == "风险筛查" and item == "具体计划" and not item_evidence and denial_evidence:
                item_evidence = denial_evidence
                covered_by_denial.append(item)

            if item_evidence:
                hit.append(item)
                evidence[item] = item_evidence
                item_scores[item] = item_score
            else:
                miss.append(item)

        ratio = len(hit) / max(1, len(cfg["items"]))
        score = round(cfg["weight"] * ratio, 1)
        result[dim] = {
            "score": score,
            "weight": cfg["weight"],
            "hit": hit,
            "miss": miss,
            "evidence": evidence,
            "item_scores": item_scores,
            "covered_by_denial": covered_by_denial,
        }
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

    next_items = flatten_score_misses(score_result, limit=4)
    if next_items:
        next_lines = [f"- 优先补问：{next_items[0]}。建议问：“{suggest_question_for_missing(next_items[0])}”"]
        if len(next_items) > 1:
            next_lines.append("- 备选补问：" + "、".join(next_items[1:4]))
    else:
        next_lines = ["- 核心问诊覆盖较好，可进入阶段性总结、诊断思路表达和SOAP整理。"]

    feedback = f"""
### 总分：{total:.1f}/100

#### 一、表现亮点
{chr(10).join([f"- {x}较好，说明问诊中已关注该维度。" for x in strong[:3]]) if strong else '- 目前问诊信息较少，建议继续补充核心病史。'}

#### 二、主要不足
{chr(10).join([f"- {x}" for x in weak[:4]]) if weak else '- 暂未发现明显短板，可进一步提高问诊系统性。'}

#### 三、下一步建议
{chr(10).join(next_lines)}

> 本评分为教学训练用途，不用于真实医疗诊断。
"""
    return feedback


def md_escape(text) -> str:
    """Avoid breaking Markdown tables when case text contains separators."""
    return str(text if text not in (None, "") else "未填写").replace("|", "｜").replace("\n", " ")


def markdown_bullets(items: List[str], fallback: str = "暂无") -> str:
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if not cleaned:
        return f"- {fallback}"
    return "\n".join(f"- {item}" for item in cleaned)


def score_dimension_table(score_result: Dict) -> str:
    rows = ["| 维度 | 得分 | 已覆盖 | 待补充 |", "| --- | ---: | --- | --- |"]
    for dimension, value in score_result.items():
        score = float(value.get("score", 0) or 0)
        weight = float(value.get("weight", 0) or 0)
        hits = "、".join(value.get("hit", [])[:5]) or "暂无"
        misses = "、".join(value.get("miss", [])[:5]) or "已基本覆盖"
        rows.append(
            f"| {md_escape(dimension)} | {score:.1f}/{weight:.0f} | "
            f"{md_escape(hits)} | {md_escape(misses)} |"
        )
    return "\n".join(rows)


def training_level_label(total_score: float, completion: Dict) -> str:
    if not completion.get("ready"):
        return "继续问诊"
    if total_score >= 85:
        return "完成度较高"
    if total_score >= 70:
        return "基本达标"
    return "可提交但仍需复盘补强"


def scale_review_lines(scale_assessments: Dict, case: Dict, history: List[Dict]) -> List[str]:
    summary = build_scale_summary(scale_assessments, case, history)
    lines = []
    recommendations = summary.get("recommendations", [])
    if recommendations:
        rec_text = "；".join(
            f"{item['priority']}：{CLINICIAN_SCALE_CONFIG[item['key']]['label']}"
            for item in recommendations
        )
        lines.append(f"系统推荐量表：{rec_text}。")

    hamd = summary["hamd17"]
    if hamd["total"] is not None:
        lines.append(f"HAMD-17：本轮逐项教学评分 {hamd['total']} 分，已完成 17/17 项。")
    elif hamd["progress"]:
        lines.append(
            f"HAMD-17：已记录 {hamd['progress']}/{hamd['total_items']} 项，"
            f"当前小计 {hamd['partial_total']} 分，尚不能作为正式总分。"
        )
    else:
        lines.append("HAMD-17：本轮尚未记录逐项教学评分。")

    hama = summary["hama"]
    if hama["total"] is not None:
        compare = ""
        if hama.get("difference") is not None:
            compare = f"，与病例库参考分相差 {hama['difference']:+.0f} 分"
        lines.append(f"HAMA：本轮逐项教学评分 {hama['total']} 分，已完成 14/14 项{compare}。")
    elif hama["progress"]:
        lines.append(
            f"HAMA：已记录 {hama['progress']}/{hama['total_items']} 项，"
            f"当前小计 {hama['partial_total']} 分，尚不能作为正式总分。"
        )
    else:
        lines.append("HAMA：本轮尚未记录逐项教学评分。")

    evidence_notes = []
    for key, label in (("hamd17", "HAMD-17"), ("hama", "HAMA")):
        evidence = summary[key]["evidence"]
        if evidence["covered"]:
            evidence_notes.append(f"{label}已有访谈依据：{'、'.join(evidence['covered'][:4])}")
        if evidence["missing"]:
            evidence_notes.append(f"{label}证据待补：{'、'.join(evidence['missing'][:4])}")
    lines.extend(evidence_notes[:4])
    return lines


def build_training_review_report(
    active_chat: Dict,
    selected_case: Dict,
    history: List[Dict],
    score_result: Dict,
    completion: Dict,
) -> str:
    """Build a deterministic teaching-review report for the current training loop."""
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_score = round(sum(v.get("score", 0) for v in score_result.values()), 1)
    level = training_level_label(total_score, completion)
    required_result = score_result.get("病例必问点覆盖", {})
    required_hit = required_result.get("hit", [])
    required_miss = required_result.get("miss", [])
    risk_result = score_result.get("风险筛查", {})
    tcm_result = score_result.get("中医辨证信息采集", {})
    top_misses = flatten_score_misses(score_result, limit=6)
    next_question = (
        suggest_question_for_missing(top_misses[0])
        if top_misses
        else "可请学生做阶段性总结，并说明诊断、证型和风险判断依据。"
    )
    scale_lines = scale_review_lines(
        active_chat.get("scale_assessments"),
        selected_case,
        history,
    )
    soap = active_chat.get("soap", "")
    soap_status = "已生成 SOAP 病历，可用于书写质量复盘。" if soap else "尚未生成 SOAP 病历。建议生成后再进行病历书写质量讨论。"
    soap_sections = []
    if soap:
        for section in ["S", "O", "A", "P", "关于量表", "教学提示"]:
            soap_sections.append(f"{section}：{'已出现' if section in soap else '建议检查是否完整'}")

    standard_info = [
        f"病例：{selected_case.get('title', active_chat.get('case_title', '未命名病例'))}",
        f"主诉：{selected_case.get('chief_complaint', '未填写')}",
        f"西医诊断大类：{get_case_diagnosis(selected_case)}",
        f"原始诊断：{selected_case.get('western_diagnosis', {}).get('raw_diagnosis', '未填写')}",
        f"中医证型：{get_case_syndrome(selected_case)}",
        f"风险等级：{selected_case.get('risk_level', '需进一步评估')}",
        f"舌象：{selected_case.get('tcm_info', {}).get('tongue', '未填写')}",
        f"脉象：{selected_case.get('tcm_info', {}).get('pulse', '未填写')}",
    ]

    risk_comment = []
    risk_level = selected_case.get("risk_level", "")
    if risk_result.get("hit"):
        risk_comment.append("已覆盖：" + "、".join(risk_result["hit"]))
    if risk_result.get("miss"):
        risk_comment.append("待补充：" + "、".join(risk_result["miss"]))
    if any(key in risk_level for key in ["中", "高", "危", "自杀", "自伤"]) and "自杀意念" in risk_result.get("miss", []):
        risk_comment.append("病例提示存在中高风险线索，但本轮尚未主动筛查自杀意念，应作为优先整改点。")

    report = f"""# 训练闭环 2.1 综合复盘报告

生成时间：{generated_at}
训练状态：{level}
问诊轮数：{len(history)} 轮
综合得分：{total_score:.1f}/100

## 一、病例库标准对照
{markdown_bullets(standard_info)}

> 当前版本尚未单独采集“学生最终诊断/证型判断”字段。本报告先对问诊覆盖、风险筛查、量表依据和 SOAP 书写进行对照复盘。

## 二、问诊评分总览
{score_dimension_table(score_result)}

## 三、病例必问点覆盖
已覆盖：
{markdown_bullets(required_hit, "暂无明确覆盖")}

待补充：
{markdown_bullets(required_miss, "病例必问点已基本覆盖")}

## 四、风险筛查复盘
{markdown_bullets(risk_comment, "当前未形成明确风险筛查记录，建议继续核对自伤自杀、冲动行为、具体计划和保护因素。")}

## 五、中医四诊与辨证信息
已采集：
{markdown_bullets(tcm_result.get("hit", []), "暂无明确采集")}

待补充：
{markdown_bullets(tcm_result.get("miss", []), "中医辨证信息已基本覆盖")}

## 六、量表评估复盘
{markdown_bullets(scale_lines)}

## 七、SOAP 病历状态
- {soap_status}
{markdown_bullets(soap_sections, "SOAP 生成后可检查 S/O/A/P、量表记录和教学提示是否齐全。")}

## 八、下一步教学建议
- 优先补强：{top_misses[0] if top_misses else "训练覆盖较完整"}
- 可直接追问：{next_question}
- 课堂复盘建议：请学生说明“为什么这样诊断、如何辨证、风险等级如何判断、量表分数依据来自哪几句访谈”。

> 本报告仅用于医学教学训练与复盘，不用于真实临床诊疗。
"""
    return report


def generate_soap(history: List[Dict], case: Dict, model: str, scale_assessments: Dict = None) -> str:
    dialogue = "\n".join([f"医生：{h['doctor']}\n患者：{h['patient']}" for h in history])
    scale_record = scale_summary_markdown(scale_assessments, case, history)
    prompt = f"""
你是一名中医精神心理科教学督导。请根据以下模拟问诊记录，生成教学用SOAP病历。
要求：
1. 仅根据对话中已经问到的信息书写。
2. 对未问到的信息写“未询及”。
3. A部分可结合病例标准答案给出“教学提示”，但要注明“模拟教学”。
4. 不要写成真实处方，不要替代医生诊疗。
5. 关于量表：严格依据“本轮结构化量表记录”书写。病例库参考分只能放在教学提示中，不能伪装成学生本轮已经测得。

【病例标准信息】
{json.dumps(prepare_case_for_prompt(case), ensure_ascii=False, indent=2)}

【问诊记录】
{dialogue}

【本轮结构化量表记录】
{scale_record}

请按以下格式输出：
S 主观资料：
O 客观资料：
A 评估：
P 计划：
关于量表：
教学提示：
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        answer = call_ollama(messages, model=model, temperature=0.2)
    except ModelCallError as error:
        log_event("soap_generation_fallback", model=model, error=str(error))
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

### 关于量表
{scale_record}

> 当前为模板病历。连接模型后可自动生成更完整的教学SOAP。
"""
    return answer


def text_to_html(text: str) -> str:
    return html_escape(str(text or "")).replace("\n", "<br/>")


def render_figma_chat_header(selected_case: Dict, active_chat: Dict, model: str) -> None:
    case_id = selected_case.get("case_id", active_chat.get("case_title", "")).replace("case_", "病例")
    st.markdown(
        f"""
        <div class="figma-chat-header">
            <div class="figma-header-left">
                <span class="figma-workspace-title">神志病科AI问诊训练工作台</span>
                <div class="figma-tag-row">
                    <span class="figma-tag"><strong>当前病例：</strong>{html_escape(case_id)}</span>
                    <span class="figma-tag">{html_escape(get_case_syndrome(selected_case))}</span>
                    <span class="figma-tag"><strong>模型：</strong>{html_escape(model)}</span>
                </div>
            </div>
            <div class="figma-header-actions">
                <span style="color:#9ca3af;font-size:0.75rem;">当前轮次</span>
                <span class="figma-round-select">全部回合 ▾</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_figma_message(role: str, turn_number: int, content: str) -> None:
    role_class = "doctor" if role == "doctor" else "patient"
    role_name = "医生" if role == "doctor" else "患者"
    role_avatar = "医" if role == "doctor" else "患"
    st.markdown(
        f"""
        <div class="figma-message-row {role_class}">
            <div class="figma-avatar {role_class}">{role_avatar}</div>
            <div class="figma-message-stack">
                <div class="figma-message-meta">第{turn_number}轮 · {role_name}</div>
                <div class="figma-bubble {role_class}">{text_to_html(content)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_figma_review_tools(
    active_chat: Dict,
    selected_case: Dict,
    history: List[Dict],
    score_result: Dict,
    completion_status: Dict,
    model: str,
    export_data: Dict,
) -> None:
    with st.expander("训练复盘与 SOAP 病历", expanded=False):
        st.caption("整合规则评分、病例必问点、量表依据、病例标准信息和 SOAP 状态。")
        if st.button(
            "生成综合复盘报告",
            use_container_width=True,
            key=f"generate_review_report_{st.session_state.active_chat_id}",
        ):
            active_chat["review_report"] = build_training_review_report(
                active_chat,
                selected_case,
                history,
                score_result,
                completion_status,
            )
            active_chat["review_report_generated_at"] = datetime.now().strftime("%m-%d %H:%M")
            active_chat["updated_at"] = active_chat["review_report_generated_at"]
            persist_chat_sessions()
            log_event("review_report_generated", chat_id=st.session_state.active_chat_id)
            st.rerun()

        if active_chat.get("review_report"):
            st.markdown(active_chat["review_report"])
        else:
            st.markdown(
                "<div class='review-placeholder'>可生成一份完整复盘报告，用于课堂讲评或项目组讨论。</div>",
                unsafe_allow_html=True,
            )

        if st.button("查看评分摘要", use_container_width=True, key=f"generate_report_{st.session_state.active_chat_id}"):
            st.markdown(generate_rule_feedback(score_result))

        if not completion_status["ready"]:
            st.caption("请补充：" + "、".join(completion_status["missing"]))

        if st.button("生成病历", use_container_width=True, key=f"generate_soap_{st.session_state.active_chat_id}"):
            if not completion_status["ready"]:
                st.warning("暂不能生成 SOAP，请先补充：" + "、".join(completion_status["missing"]))
            else:
                active_chat["soap"] = generate_soap(
                    history,
                    selected_case,
                    model=model,
                    scale_assessments=active_chat.get("scale_assessments"),
                )
                active_chat["review_report"] = ""
                active_chat["review_report_generated_at"] = ""
                persist_chat_sessions()
                log_event("soap_generated", chat_id=st.session_state.active_chat_id)

        if active_chat.get("soap"):
            st.markdown(active_chat["soap"])


# ---------------- UI ----------------
inject_custom_css()
ensure_startup_maintenance()

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

active_chat = normalize_chat_session(get_active_chat(), default_case_title)
persist_chat_sessions()

# 防止某个病例文件被删除、改名后出错。
if active_chat["case_title"] not in case_options:
    active_chat["case_title"] = default_case_title
    persist_chat_sessions()
    log_event("missing_case_recovered", chat_id=st.session_state.active_chat_id)

selected_case = case_options[active_chat["case_title"]]
model = active_chat.get("model", "deepseek-v4-flash")
history = active_chat["history"]
active_chat.setdefault("soap", "")
active_chat.setdefault("review_report", "")
active_chat.setdefault("review_report_generated_at", "")
active_chat.setdefault("score_log", [])
active_chat.setdefault("training_submitted", False)
active_chat.setdefault("submitted_at", "")
active_chat.setdefault("completion_snapshot", {})
active_chat["scale_assessments"] = normalize_scale_assessments(active_chat.get("scale_assessments"))
active_chat.setdefault("show_supervisor_history", False)
active_chat.setdefault("open_supervisor_history_once", False)
active_chat.setdefault("supervisor_history_revision", 0)
active_chat.setdefault("supervisor_feedback_page", 0)
active_chat.setdefault("case_widget_revision", 0)
active_chat.setdefault("pending_patient_retry", {})
active_chat.setdefault("request_state", {})

# 兼容部分原有逻辑。
st.session_state.history = history

render_chat_sidebar(default_case_title, active_chat, cases)

score_result, score_detail = score_dialogue(history, selected_case)
total_score = sum(v["score"] for v in score_result.values())
completion_status = evaluate_training_completion(history, selected_case, score_result)
export_data = {
    "case": selected_case,
    "history": history,
    "score": score_result,
    "supervisor_history": active_chat.get("supervisor_history", []),
    "score_log": active_chat.get("score_log", []),
    "training_submitted": active_chat.get("training_submitted", False),
    "submitted_at": active_chat.get("submitted_at", ""),
    "review_report": active_chat.get("review_report", ""),
    "review_report_generated_at": active_chat.get("review_report_generated_at", ""),
    "completion": completion_status,
    "scale_assessments": active_chat.get("scale_assessments", {}),
    "scale_summary": build_scale_summary(
        active_chat.get("scale_assessments"), selected_case, history
    ),
    "training_targets": {
        "required_questions": get_case_required_questions(selected_case),
        "risk_level": selected_case.get("risk_level", "需进一步评估"),
        "syndrome": get_case_syndrome(selected_case),
        "diagnosis_category": get_case_diagnosis(selected_case),
    },
}

main_col, score_col = st.columns([1, 0.32], gap="small", vertical_alignment="top")

with main_col:
    with st.container(border=False, key=f"figma_chat_area_{st.session_state.active_chat_id}"):
        render_figma_chat_header(selected_case, active_chat, model)

        with st.container(
            border=False,
            key=f"figma_chat_scroll_{st.session_state.active_chat_id}",
        ):
            if history:
                visible_turns = min(
                    len(history),
                    st.session_state.chat_visible_turns.setdefault(
                        st.session_state.active_chat_id, CHAT_RENDER_BATCH_SIZE
                    ),
                )
                hidden_turns = len(history) - visible_turns
                if hidden_turns > 0:
                    if st.button(
                        f"加载更早记录（还有 {hidden_turns} 轮）",
                        use_container_width=True,
                        key=f"load_earlier_{st.session_state.active_chat_id}_{visible_turns}",
                    ):
                        st.session_state.chat_visible_turns[st.session_state.active_chat_id] = (
                            visible_turns + CHAT_RENDER_BATCH_SIZE
                        )
                        st.rerun()

                for turn_number, h in enumerate(
                    history[-visible_turns:],
                    start=hidden_turns + 1,
                ):
                    render_figma_message("doctor", turn_number, h.get("doctor", ""))
                    render_figma_message("patient", turn_number, h.get("patient", ""))

                    if h.get("tongue_images"):
                        for img in h["tongue_images"]:
                            if os.path.exists(img):
                                st.image(img, caption="当前病例舌象参考图", width=360)
                            else:
                                st.warning(f"未找到舌象图片：{img}")

                    if h.get("score_event"):
                        with st.expander("本轮问诊评分", expanded=False):
                            render_turn_score_event(h["score_event"])
            else:
                st.markdown(
                    "<div class='figma-empty-state'>问诊记录会显示在这里。请在下方输入第一句问诊。</div>",
                    unsafe_allow_html=True,
                )

        patient_question = ""
        patient_submitted = False
        with st.container(
            border=False,
            key=f"figma_composer_{st.session_state.active_chat_id}",
        ):
            with st.form(
                key=f"patient_form_{st.session_state.active_chat_id}",
                clear_on_submit=True,
                border=False,
            ):
                input_col, mic_col, send_col = st.columns([0.86, 0.07, 0.07], gap="small", vertical_alignment="center")
                with input_col:
                    patient_question = st.text_input(
                        "学生问诊输入",
                        placeholder="输入您的回复消息...",
                        label_visibility="collapsed",
                    )
                with mic_col:
                    st.markdown(
                        """
                        <div class="figma-mic-button" aria-label="语音输入">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                                 stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>
                                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                                <line x1="12" y1="19" x2="12" y2="22"/>
                            </svg>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with send_col:
                    patient_submitted = st.form_submit_button("➤", help="发送问诊", use_container_width=True)

        pending_patient_retry = active_chat.get("pending_patient_retry") or {}
        if pending_patient_retry:
            st.warning(
                "患者回答生成失败，本次问题没有写入问诊记录。"
                f"可以重新生成：{pending_patient_retry.get('question', '')}"
            )
            retry_col, dismiss_col = st.columns([1, 1])
            with retry_col:
                retry_patient_answer = st.button(
                    "重新生成患者回答",
                    use_container_width=True,
                    key=f"retry_patient_{st.session_state.active_chat_id}",
                )
            with dismiss_col:
                dismiss_patient_retry = st.button(
                    "取消本次重试",
                    use_container_width=True,
                    key=f"dismiss_patient_{st.session_state.active_chat_id}",
                )
            if dismiss_patient_retry:
                active_chat["pending_patient_retry"] = {}
                persist_chat_sessions()
                st.rerun()
            if retry_patient_answer:
                with st.status("患者Agent正在重新生成回答...", expanded=False) as status:
                    retry_succeeded = submit_question(
                        pending_patient_retry.get("question", ""),
                        selected_case,
                        model,
                        active_chat,
                    )
                    if retry_succeeded:
                        status.update(label="患者Agent已生成回答", state="complete")
                    else:
                        status.update(label="生成失败，可以稍后再次重试", state="error")
                st.rerun()

        if patient_submitted:
            if patient_question.strip():
                with st.status("患者Agent正在读取病例角色卡并组织回答...", expanded=False) as status:
                    generation_succeeded = submit_question(
                        patient_question, selected_case, model, active_chat
                    )
                    if generation_succeeded:
                        status.update(label="患者Agent已生成回答", state="complete")
                    else:
                        status.update(label="生成失败，可以重新生成", state="error")
                st.rerun()
            else:
                st.warning("请输入问诊问题。")

with score_col:
    with st.container(
        border=False,
        key=f"figma_score_panel_{st.session_state.active_chat_id}",
    ):
        render_score_panel(score_result, total_score)

        supervisor_tab, scale_tab, score_tab, case_tab = st.tabs(
            ["督导老师", "量表评估", "评分详情", "病例资料"]
        )

        with supervisor_tab:
            st.caption("围绕当前病例和问诊记录提问，督导老师会结合评分结果给出教学反馈。")

            with st.form(key=f"supervisor_form_{st.session_state.active_chat_id}"):
                supervisor_input_col, supervisor_send_col = st.columns([0.86, 0.14], gap="small", vertical_alignment="center")
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
            should_open_supervisor_history = active_chat.pop("open_supervisor_history_once", False)
            feedback_count = len(supervisor_history)
            with st.expander(
                f"历史反馈 · {feedback_count}条",
                expanded=should_open_supervisor_history or bool(supervisor_history),
            ):
                if supervisor_history:
                    feedback_page = min(
                        active_chat.get("supervisor_feedback_page", 0),
                        feedback_count - 1,
                    )
                    active_chat["supervisor_feedback_page"] = feedback_page
                    newer_col, page_col, older_col = st.columns([1, 1.1, 1])
                    with newer_col:
                        if st.button(
                            "← 上一条",
                            disabled=feedback_page <= 0,
                            key=f"newer_feedback_{st.session_state.active_chat_id}_{feedback_page}",
                            use_container_width=True,
                        ):
                            active_chat["supervisor_feedback_page"] = feedback_page - 1
                            st.rerun()
                    with page_col:
                        st.markdown(
                            f"<div class='feedback-page-indicator'>第 {feedback_page + 1} / {feedback_count} 条</div>",
                            unsafe_allow_html=True,
                        )
                    with older_col:
                        if st.button(
                            "下一条 →",
                            disabled=feedback_page >= feedback_count - 1,
                            key=f"older_feedback_{st.session_state.active_chat_id}_{feedback_page}",
                            use_container_width=True,
                        ):
                            active_chat["supervisor_feedback_page"] = feedback_page + 1
                            st.rerun()

                    item = list(reversed(supervisor_history))[feedback_page]
                    created_at = item.get("created_at", "")
                    st.markdown(
                        f"<div class='agent-bubble-student'><b>学生：</b>{html_escape(item['student'])}<br/><span class='compact-caption'>{html_escape(created_at)}</span></div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div class='agent-bubble-supervisor'><b>督导：</b>{html_escape(item['supervisor'])}</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("还没有向督导老师提问。")

            with st.expander("下一步建议", expanded=True):
                render_next_step_panel(selected_case, history, score_result)

            render_figma_review_tools(
                active_chat,
                selected_case,
                history,
                score_result,
                completion_status,
                model,
                export_data,
            )

        with scale_tab:
            render_scale_assessment_panel(active_chat, selected_case, history)

        with score_tab:
            with st.expander("查看各维度评分明细", expanded=True):
                render_score_detail_panel(score_result)

        with case_tab:
            with st.expander("病例训练目标", expanded=True):
                render_case_target_panel(selected_case)

            with st.expander("当前病例标准信息与舌象", expanded=False):
                st.write(f"主诉：{selected_case.get('chief_complaint', '未填写')}")
                st.write(f"教学证型：{selected_case.get('tcm_info', {}).get('syndrome', '未填写')}")
                st.write(f"诊断大类：{get_case_diagnosis(selected_case)}")
                st.write(f"风险：{selected_case.get('risk_level', '需进一步评估')}")
                tongue_preview = get_tongue_images(selected_case)
                if tongue_preview:
                    for img in tongue_preview:
                        st.image(img, caption="舌象参考图", width=240)

persist_chat_sessions()
