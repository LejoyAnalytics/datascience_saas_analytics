"""
Floating chatbot widget — bottom-right, available on every page.

Pure UI + orchestration: the question-answering pipeline lives in
chatbot_engine.py (Groq calls + safe SQL), which is the only place that
talks to Groq or the database for the chatbot. This module never sees
GROQ_API_KEY.

Message bubbles are hand-built HTML (not st.chat_message) so every color
is driven explicitly by the active palette — Streamlit's native chat
component renders text using its static server-side theme regardless of
our light/dark toggle, which is what made replies unreadable in light mode.
"""

from __future__ import annotations

import html

import streamlit as st

from chatbot_engine import answer_question
from theme import get_palette, hex_to_rgba

SUGGESTED_QUESTIONS = {
    "dashboard": [
        "What is the current revenue?",
        "Which customer segment generates the most revenue?",
    ],
    "forecast": [
        "What is the revenue forecast for the next 3 months?",
        "How accurate is the revenue forecast?",
    ],
    "about": [
        "What data is available in this application?",
        "What does CloudFlow's business model look like?",
    ],
}

PAGE_LABELS = {"about": "Business Overview", "dashboard": "Dashboard", "forecast": "Revenue Forecast"}


def _inject_chatbot_css(p) -> None:
    user_bubble_bg = hex_to_rgba(p.accent_purple, 0.16)
    st.markdown(
        f"""
        <style>
        div[class*="st-key-chatbot-toggle"] {{
            position: fixed; bottom: 24px; right: 24px; z-index: 1001; width: auto;
        }}
        div[class*="st-key-chatbot-toggle"] button {{
            width: 56px; height: 56px; border-radius: 50%; font-size: 1.4rem; padding: 0;
            background: {p.gradient_primary} !important; color: white !important; border: none !important;
            box-shadow: 0 8px 24px rgba(124,58,237,0.45);
            transition: transform 0.15s ease;
        }}
        div[class*="st-key-chatbot-toggle"] button:hover {{ transform: scale(1.07); }}

        div[class*="st-key-chatbot-panel"] {{
            position: fixed; bottom: 92px; right: 24px; z-index: 1000;
            width: 400px; max-height: 72vh; overflow-y: auto;
            background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 18px;
            box-shadow: 0 24px 64px rgba(0,0,0,0.45);
            padding: 0 16px 10px 16px;
        }}

        div[class*="st-key-chatbot-header"] {{
            position: sticky; top: 0; z-index: 2; background: {p.surface};
            padding: 14px 0 10px 0; margin-bottom: 4px; border-bottom: 1px solid {p.border};
        }}
        .chat-header-row {{ display: flex; align-items: center; gap: 10px; }}
        .chat-header-avatar {{
            width: 30px; height: 30px; border-radius: 50%; flex-shrink: 0;
            background: {p.gradient_primary}; display: flex; align-items: center; justify-content: center;
            font-size: 0.85rem;
        }}
        .chat-header-title {{ font-weight: 700; font-size: 0.92rem; color: {p.text_primary}; line-height: 1.2; }}
        .chat-header-sub {{ font-size: 0.7rem; color: {p.text_muted}; margin-top: 1px; }}

        .chat-suggest-label {{ font-size: 0.72rem; color: {p.text_muted}; margin: 10px 0 8px 2px; }}
        div[class*="st-key-chat-suggest-"] {{ margin-bottom: 6px; }}
        div[class*="st-key-chat-suggest-"] button {{
            text-align: left; background: {p.table_header_bg} !important; border: 1px solid {p.border} !important;
            color: {p.text_secondary} !important; font-size: 0.8rem; border-radius: 12px; padding: 9px 12px;
            width: 100%; white-space: normal; height: auto;
        }}
        div[class*="st-key-chat-suggest-"] button:hover {{
            background: {p.table_row_hover} !important; color: {p.text_primary} !important; border-color: {p.border_strong} !important;
        }}

        div[class*="st-key-chatbot-close"] button {{
            width: 26px; height: 26px; min-height: 26px; border-radius: 50%; padding: 0; font-size: 0.72rem;
            background: transparent !important; border: 1px solid {p.border} !important; color: {p.text_muted} !important;
        }}
        div[class*="st-key-chatbot-close"] button:hover {{ color: {p.text_primary} !important; border-color: {p.border_strong} !important; }}

        /* --- ChatGPT-style message rows: plain assistant text, bubble for user --- */
        .chat-row {{ display: flex; gap: 8px; margin: 0 0 16px 0; align-items: flex-start; }}
        .chat-row-user {{ justify-content: flex-end; }}
        .chat-bubble-user {{
            background: {user_bubble_bg}; color: {p.text_primary};
            padding: 9px 14px; border-radius: 16px; border-bottom-right-radius: 4px;
            max-width: 82%; font-size: 0.85rem; line-height: 1.55; white-space: pre-wrap; word-wrap: break-word;
        }}
        .chat-avatar-assistant {{
            width: 24px; height: 24px; border-radius: 50%; flex-shrink: 0; margin-top: 1px;
            background: {p.gradient_primary}; display: flex; align-items: center; justify-content: center; font-size: 0.7rem;
        }}
        .chat-assistant-text {{
            color: {p.text_primary} !important; font-size: 0.85rem; line-height: 1.6;
            padding-top: 2px; max-width: 84%; white-space: pre-wrap; word-wrap: break-word;
        }}

        /* Native spinner + text input + submit button — forced to follow the active palette,
           since Streamlit renders these using its static server-side theme otherwise. */
        div[class*="st-key-chatbot-panel"] [data-testid="stSpinner"] * {{ color: {p.text_secondary} !important; }}
        div[class*="st-key-chatbot-form"] {{ position: sticky; bottom: 0; background: {p.surface}; padding-top: 8px; }}
        div[class*="st-key-chatbot-form"] div[data-testid="stTextInput"] input {{
            border-radius: 20px !important; background: {p.table_header_bg} !important;
            border: 1px solid {p.border} !important; color: {p.text_primary} !important;
            font-size: 0.85rem !important;
        }}
        div[class*="st-key-chatbot-form"] div[data-testid="stTextInput"] input::placeholder {{ color: {p.text_muted} !important; }}
        div[class*="st-key-chatbot-form"] button {{
            border-radius: 50% !important; width: 38px; height: 38px; min-height: 38px; padding: 0;
            background: {p.gradient_primary} !important; color: white !important; border: none !important;
            font-size: 0.95rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _bubble_html(role: str, content: str) -> str:
    safe = html.escape(content).replace("\n", "<br>")
    if role == "user":
        return f"<div class='chat-row chat-row-user'><div class='chat-bubble-user'>{safe}</div></div>"
    return (
        "<div class='chat-row'>"
        "<div class='chat-avatar-assistant'>✨</div>"
        f"<div class='chat-assistant-text'>{safe}</div>"
        "</div>"
    )


def _ask(question: str, page_context: str) -> None:
    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.spinner("Thinking..."):
        try:
            answer = answer_question(question, page_context=page_context)
        except Exception as e:
            answer = f"Sorry, something went wrong: {e}"
    st.session_state.chat_history.append({"role": "assistant", "content": answer})


def render_floating_chatbot(current_page: str) -> None:
    palette = get_palette()
    _inject_chatbot_css(palette)

    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    with st.container(key="chatbot-toggle"):
        icon = "✕" if st.session_state.chat_open else "\U0001F4AC"
        if st.button(icon, key="chatbot-toggle-btn", help="Chat with the CloudFlow Assistant"):
            st.session_state.chat_open = not st.session_state.chat_open
            st.rerun()

    if not st.session_state.chat_open:
        return

    with st.container(key="chatbot-panel"):
        with st.container(key="chatbot-header"):
            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown(
                    "<div class='chat-header-row'>"
                    "<div class='chat-header-avatar'>✨</div>"
                    "<div><div class='chat-header-title'>CloudFlow Assistant</div>"
                    "<div class='chat-header-sub'>Ask me anything — general or about your data</div></div>"
                    "</div>",
                    unsafe_allow_html=True,
                )
            with col2:
                with st.container(key="chatbot-close"):
                    if st.button("✕", key="chatbot-close-btn"):
                        st.session_state.chat_open = False
                        st.rerun()

        if not st.session_state.chat_history:
            page_label = PAGE_LABELS.get(current_page, "this page")
            st.markdown(f"<div class='chat-suggest-label'>Try asking, from {page_label}:</div>", unsafe_allow_html=True)
            for i, q in enumerate(SUGGESTED_QUESTIONS.get(current_page, [])):
                with st.container(key=f"chat-suggest-{i}"):
                    if st.button(q, key=f"chat-suggest-btn-{i}"):
                        _ask(q, page_label)
                        st.rerun()

        for msg in st.session_state.chat_history:
            st.markdown(_bubble_html(msg["role"], msg["content"]), unsafe_allow_html=True)

        with st.form(key="chatbot-form", clear_on_submit=True, border=False):
            fcol1, fcol2 = st.columns([5, 1])
            with fcol1:
                user_text = st.text_input(
                    "Message", key="chatbot_text_input", label_visibility="collapsed",
                    placeholder="Message CloudFlow Assistant…",
                )
            with fcol2:
                submitted = st.form_submit_button("➤")

        if submitted and user_text and user_text.strip():
            _ask(user_text.strip(), PAGE_LABELS.get(current_page, current_page))
            st.rerun()
