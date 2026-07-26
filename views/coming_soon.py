"""Shared placeholder page for nav items that aren't built yet."""

import streamlit as st

from theme import get_palette, page_header


def render(title: str, icon: str, description: str):
    palette = get_palette()
    page_header("Roadmap", title, description)

    st.markdown(
        f"""
        <div style="
            display:flex; flex-direction:column; align-items:center; justify-content:center;
            text-align:center; gap:14px; padding: 72px 24px;
            background: {palette.surface}; border: 1px dashed {palette.border_strong};
            border-radius: 16px;
        ">
            <div style="font-size:2.4rem;">{icon}</div>
            <div style="font-size:1.15rem; font-weight:700; color:{palette.text_primary};">{title} is on the roadmap</div>
            <div style="max-width:480px; color:{palette.text_secondary}; font-size:0.92rem; line-height:1.6;">
                This module isn't wired up to live data yet — check back soon.
            </div>
            <div style="
                margin-top:6px; padding: 4px 14px; border-radius: 20px; font-size:0.72rem; font-weight:700;
                letter-spacing:0.04em; text-transform:uppercase;
                background: {palette.warning_soft}; color: {palette.warning};
            ">Coming soon</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
