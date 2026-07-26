"""
Shared design system for the dashboard — two full palettes (dark/light),
Plotly styling, CSS injection, and small UI components (KPI cards,
sparklines, page headers, styled tables, the theme toggle).

Pure presentation. Nothing here touches data, MySQL, or the pipeline — every
page imports this module and calls into src/data_access.py separately for
numbers.

Theme switching: st.session_state["theme_mode"] ("dark" or "light") is the
single source of truth, set by theme_toggle() in the sidebar. Every view
calls get_palette() once per render and threads the returned Palette through
to chart_layout()/kpi_card()/etc., so charts and CSS are rebuilt fresh with
the right colors on every rerun — no reliance on client-side theme state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import plotly.graph_objects as go
import streamlit as st

from info_panel import info_button


@dataclass(frozen=True)
class Palette:
    mode: str
    bg: str
    surface: str
    surface_raised: str
    sidebar_bg: str
    border: str
    border_strong: str
    text_primary: str
    text_secondary: str
    text_muted: str
    gradient_primary: str
    gradient_secondary: str
    positive: str
    positive_soft: str
    warning: str
    warning_soft: str
    negative: str
    negative_soft: str
    neutral_soft: str
    accent_blue: str
    accent_cyan: str
    accent_purple: str
    accent_pink: str
    plotly_template: str
    gridline: str
    table_header_bg: str
    table_row_hover: str
    chart_categorical: list[str] = field(default_factory=list)


DARK = Palette(
    mode="dark",
    bg="#0b0e14", surface="#141824", surface_raised="#181d2b", sidebar_bg="#0d1017",
    border="rgba(255,255,255,0.08)", border_strong="rgba(255,255,255,0.14)",
    text_primary="#f5f5f7", text_secondary="#9aa0ac", text_muted="#6b7280",
    gradient_primary="linear-gradient(135deg, #7c3aed 0%, #2563eb 100%)",
    gradient_secondary="linear-gradient(135deg, #2563eb 0%, #06b6d4 100%)",
    positive="#10b981", positive_soft="rgba(16,185,129,0.15)",
    warning="#f59e0b", warning_soft="rgba(245,158,11,0.15)",
    negative="#ef4444", negative_soft="rgba(239,68,68,0.15)",
    neutral_soft="rgba(154,160,172,0.15)",
    accent_blue="#3b82f6", accent_cyan="#06b6d4", accent_purple="#8b5cf6", accent_pink="#ec4899",
    plotly_template="plotly_dark", gridline="rgba(255,255,255,0.06)",
    table_header_bg="rgba(255,255,255,0.04)", table_row_hover="rgba(255,255,255,0.04)",
)
DARK = Palette(**{**DARK.__dict__, "chart_categorical": [
    DARK.accent_blue, DARK.accent_cyan, DARK.positive, DARK.warning,
    DARK.accent_purple, DARK.accent_pink, DARK.negative,
]})

LIGHT = Palette(
    mode="light",
    bg="#f4f5f8", surface="#ffffff", surface_raised="#ffffff", sidebar_bg="#ffffff",
    border="rgba(15,23,42,0.09)", border_strong="rgba(15,23,42,0.18)",
    text_primary="#0f1115", text_secondary="#4b5563", text_muted="#64748b",
    gradient_primary="linear-gradient(135deg, #7c3aed 0%, #2563eb 100%)",
    gradient_secondary="linear-gradient(135deg, #2563eb 0%, #06b6d4 100%)",
    positive="#059669", positive_soft="rgba(5,150,105,0.12)",
    warning="#d97706", warning_soft="rgba(217,119,6,0.12)",
    negative="#dc2626", negative_soft="rgba(220,38,38,0.12)",
    neutral_soft="rgba(75,85,99,0.10)",
    accent_blue="#2563eb", accent_cyan="#0891b2", accent_purple="#7c3aed", accent_pink="#db2777",
    plotly_template="plotly_white", gridline="rgba(15,23,42,0.08)",
    table_header_bg="rgba(15,23,42,0.03)", table_row_hover="rgba(15,23,42,0.03)",
)
LIGHT = Palette(**{**LIGHT.__dict__, "chart_categorical": [
    LIGHT.accent_blue, LIGHT.accent_cyan, LIGHT.positive, LIGHT.warning,
    LIGHT.accent_purple, LIGHT.accent_pink, LIGHT.negative,
]})

CHART_CONFIG = {"displayModeBar": False, "responsive": True}


def get_palette() -> Palette:
    return LIGHT if st.session_state.get("theme_mode") == "light" else DARK


def hex_to_rgba(color: str, alpha: float) -> str:
    if color.startswith("rgb"):
        return color
    h = color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# --- Plotly styling ---------------------------------------------------------------

def chart_layout(fig: go.Figure, palette: Palette, y_title: str = "", height: int = 360, show_legend: bool = True) -> go.Figure:
    fig.update_layout(
        template=palette.plotly_template,
        height=height,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, -apple-system, Segoe UI, sans-serif", color=palette.text_secondary, size=12),
        yaxis_title=y_title,
        showlegend=show_legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=palette.surface_raised, bordercolor=palette.border_strong,
            font=dict(color=palette.text_primary, family="Inter, -apple-system, Segoe UI, sans-serif", size=12),
        ),
        colorway=palette.chart_categorical,
    )
    # tick/title colors set explicitly (not left to the plotly_dark/plotly_white
    # template defaults) — the built-in templates' own tickfont is more specific
    # than the general layout.font above and would otherwise win, regardless of mode
    axis_text = dict(color=palette.text_secondary, family="Inter, -apple-system, Segoe UI, sans-serif", size=11)
    fig.update_xaxes(
        showgrid=False, zeroline=False, showline=False,
        tickfont=axis_text, title_font=axis_text,
    )
    fig.update_yaxes(
        showgrid=True, gridcolor=palette.gridline, zeroline=False, showline=False,
        tickfont=axis_text, title_font=axis_text,
    )
    return fig


def area_trace(x, y, color: str, name: str) -> go.Scatter:
    return go.Scatter(
        x=x, y=y, name=name, mode="lines",
        line=dict(color=color, width=2.5, shape="spline", smoothing=0.3),
        fill="tozeroy", fillcolor=hex_to_rgba(color, 0.18),
    )


def sparkline_fig(values, color: str) -> go.Figure:
    fig = go.Figure(go.Scatter(
        y=list(values), mode="lines", line=dict(color=color, width=2, shape="spline", smoothing=0.3),
        fill="tozeroy", fillcolor=hex_to_rgba(color, 0.18), hoverinfo="skip",
    ))
    fig.update_layout(
        height=44, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


# --- CSS -------------------------------------------------------------------------

def inject_css(p: Palette):
    is_dark = p.mode == "dark"
    # native BaseWeb dropdown/menu chrome needs an explicit override since it's
    # a portal rendered outside .stApp and otherwise stays on config.toml's
    # static base theme regardless of our toggle
    input_bg = p.surface if is_dark else "#ffffff"
    scrollbar_thumb = "rgba(255,255,255,0.15)" if is_dark else "rgba(15,23,42,0.18)"

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
        }}

        ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
        ::-webkit-scrollbar-thumb {{ background: {scrollbar_thumb}; border-radius: 6px; }}

        .stApp {{ background: {p.bg}; }}
        .block-container {{
            padding-top: 3.25rem; padding-bottom: 3rem; max-width: 1600px;
            animation: fadeIn 0.4s ease-out;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(6px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        /* sidebar — narrow, brand pinned top, nav in the middle, toggle pinned bottom.
           Width is forced ONLY while expanded so the native collapse arrow still works —
           an unconditional !important width fights Streamlit's own collapse mechanism. */
        section[data-testid="stSidebar"] {{
            background: {p.sidebar_bg}; border-right: 1px solid {p.border}; position: relative;
        }}
        section[data-testid="stSidebar"][aria-expanded="true"] {{
            min-width: 220px !important; max-width: 220px !important; width: 220px !important;
        }}
        /* bottom-pin the toggle by position, not flexbox — deterministic regardless of how
           many wrapper divs Streamlit puts between the sidebar and the block-container */
        section[data-testid="stSidebar"] .block-container {{
            padding-top: 0.6rem; padding-bottom: 100px; animation: none;
        }}
        section[data-testid="stSidebar"] * {{ color: {p.text_primary}; text-align: left !important; }}

        /* logo shown in place of Streamlit's native re-expand control when the sidebar is
           collapsed — this is still the real, fully clickable native button, only restyled.
           width/height AND max-width/max-height are both capped defensively in case the
           testid sits on a wider wrapper than the button itself in some Streamlit builds —
           an over-wide restyle here is what was bleeding into the page and hiding content
           below it, so this must never be allowed to grow past a small fixed badge. */
        [data-testid="stSidebarCollapsedControl"] {{
            background: {p.gradient_primary} !important; border-radius: 9px !important;
            width: 34px !important; height: 34px !important;
            max-width: 34px !important; max-height: 34px !important; min-width: 34px !important;
            display: flex !important; align-items: center !important; justify-content: center !important;
            box-shadow: 0 4px 14px rgba(124,58,237,0.4); overflow: hidden; z-index: 999997;
        }}
        [data-testid="stSidebarCollapsedControl"] * {{ background: transparent !important; }}
        [data-testid="stSidebarCollapsedControl"] svg {{ display: none !important; }}
        [data-testid="stSidebarCollapsedControl"]::after {{
            content: "R"; color: white; font-weight: 800; font-size: 0.95rem; font-family: 'Inter', sans-serif;
        }}

        /* icon-only nav rail — the real sidebar's content (nav buttons, brand, toggle)
           is entirely hidden by Streamlit whenever the sidebar is collapsed, so this
           separate, always-rendered, fixed-position rail is what keeps navigation
           reachable in that state. Hidden via CSS whenever the sidebar IS expanded
           (same aria-expanded signal already used for the sidebar's own width rule),
           so it never doubles up with the full nav. */
        div[class*="st-key-navrail-wrap"] {{
            position: fixed; top: 58px; left: 12px; z-index: 999996;
            display: flex; flex-direction: column; gap: 8px;
        }}
        section[data-testid="stSidebar"][aria-expanded="true"] ~ section div[class*="st-key-navrail-wrap"],
        section[data-testid="stSidebar"][aria-expanded="true"] ~ div div[class*="st-key-navrail-wrap"] {{
            display: none !important;
        }}
        div[class*="st-key-navrailitem-"] button {{
            width: 36px; height: 36px; min-height: 36px; padding: 0; border-radius: 10px;
            font-size: 1rem; display: flex; align-items: center; justify-content: center;
            background: {p.surface} !important; border: 1px solid {p.border} !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.18);
        }}
        div[class*="st-key-navrailitem-active-"] button {{
            background: {p.gradient_primary} !important; border-color: transparent !important;
        }}

        /* top bar (main content) — MySQL live status, right-aligned, kept above any
           native chrome so it's never visually hidden underneath it */
        .topbar-status {{ text-align: right; padding-top: 2px; position: relative; z-index: 10; }}

        /* theme toggle — the button IS the pill (no overlay layer, so there's no
           chance of the visible pill and the clickable element drifting apart).
           State-dependent colors come from a container key that changes between
           "theme-toggle-day" / "theme-toggle-night" each rerun. */
        /* left+right (not right alone) so the wrap's own width is pinned to the sidebar's
           inner width, then flex justify-content pushes its child to the right edge —
           setting only `right` left it visually stuck on the left, since the wrap
           inherits Streamlit's default full-width block sizing and the button inside
           wasn't told to align to the wrap's own right side. */
        div[class*="st-key-theme-toggle-wrap"] {{
            position: absolute; left: 16px; right: 4px; bottom: 16px;
            display: flex; justify-content: flex-end;
        }}
        div[class*="st-key-theme-toggle-day"] [data-testid="stButton"],
        div[class*="st-key-theme-toggle-night"] [data-testid="stButton"] {{ width: fit-content; }}
        div[class*="st-key-theme-toggle-day"] button,
        div[class*="st-key-theme-toggle-night"] button {{
            width: auto; height: 26px; border-radius: 13px; padding: 0 10px;
            font-size: 0.68rem; font-weight: 700; letter-spacing: 0.01em;
            display: flex; align-items: center; justify-content: center; gap: 4px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.16);
            transition: background 0.35s ease, color 0.35s ease, box-shadow 0.35s ease;
        }}
        div[class*="st-key-theme-toggle-day"] button {{
            background: linear-gradient(180deg, #ffffff 0%, #eef0f4 100%) !important;
            color: #b45309 !important; border: 1px solid rgba(0,0,0,0.08) !important;
        }}
        div[class*="st-key-theme-toggle-night"] button {{
            background: linear-gradient(180deg, #1c2030 0%, #05070c 100%) !important;
            color: #c7d2fe !important; border: 1px solid rgba(255,255,255,0.08) !important;
        }}
        div[class*="st-key-theme-toggle-day"] button [data-testid="stIconMaterial"],
        div[class*="st-key-theme-toggle-night"] button [data-testid="stIconMaterial"] {{
            font-size: 0.8rem !important;
        }}

        /* st.caption anywhere in the app (sidebar + main content) */
        [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {{ color: {p.text_muted} !important; }}

        /* nav items — force left alignment on every nested element Streamlit renders
           inside the button (its own base CSS otherwise centers button content) */
        div[class*="st-key-navitem-"] {{ margin-bottom: 4px; }}
        div[class*="st-key-navitem-"] button {{
            width: 100%; text-align: left !important; border: 1px solid transparent; background: transparent;
            color: {p.text_secondary}; font-weight: 500; font-size: 0.88rem; border-radius: 10px; padding: 10px 12px;
            display: flex; align-items: center; justify-content: flex-start !important; gap: 8px;
            transition: background 0.15s ease, color 0.15s ease, transform 0.15s ease;
        }}
        div[class*="st-key-navitem-"] button * {{
            text-align: left !important; justify-content: flex-start !important; width: auto !important;
        }}
        div[class*="st-key-navitem-"] button:hover {{
            background: {p.table_row_hover}; color: {p.text_primary};
        }}
        div[class*="st-key-navitem-active"] button {{
            background: {p.gradient_primary} !important; color: white !important;
            box-shadow: 0 4px 18px rgba(124,58,237,0.35); font-weight: 600;
        }}

        /* theme toggle */
        div[class*="st-key-theme-toggle-wrap"] label p {{ color: {p.text_secondary} !important; font-size: 0.85rem; }}

        /* KPI cards */
        div[class*="st-key-kpi-"] {{
            background: {p.surface}; border: 1px solid {p.border}; border-radius: 16px;
            padding: 18px 20px 10px 20px; transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
        }}
        div[class*="st-key-kpi-"]:hover {{
            transform: translateY(-3px); border-color: {p.border_strong};
            box-shadow: 0 12px 32px rgba(0,0,0,{0.35 if is_dark else 0.10});
        }}
        div[class*="st-key-kpi-hero-"] {{
            background: {p.gradient_primary}; border: none;
            box-shadow: 0 12px 40px rgba(124,58,237,0.28);
        }}
        div[class*="st-key-kpi-hero-"]:hover {{ box-shadow: 0 16px 48px rgba(124,58,237,0.4); }}

        .kpi-label {{ font-size: 0.8rem; color: {p.text_secondary}; font-weight: 500; letter-spacing: 0.02em; }}
        div[class*="st-key-kpi-hero-"] .kpi-label {{ color: rgba(255,255,255,0.8); }}
        .kpi-value {{ font-size: 1.9rem; font-weight: 700; color: {p.text_primary}; margin: 4px 0 8px 0; line-height: 1.1; }}
        div[class*="st-key-kpi-hero-"] .kpi-value {{ color: white; }}
        .kpi-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }}
        .kpi-badge {{
            display: inline-flex; align-items: center; gap: 3px; font-size: 0.72rem; font-weight: 600;
            padding: 2px 8px; border-radius: 20px; white-space: nowrap;
        }}
        .badge-positive {{ background: {p.positive_soft}; color: {p.positive}; }}
        .badge-negative {{ background: {p.negative_soft}; color: {p.negative}; }}
        .badge-neutral {{ background: {p.neutral_soft}; color: {p.text_secondary}; }}
        div[class*="st-key-kpi-hero-"] .badge-positive {{ background: rgba(255,255,255,0.18); color: white; }}
        div[class*="st-key-kpi-hero-"] .badge-negative {{ background: rgba(255,255,255,0.18); color: white; }}

        div[class*="st-key-panel-"] {{
            background: {p.surface}; border: 1px solid {p.border}; border-radius: 16px; padding: 20px 22px;
        }}
        div[class*="st-key-forecast-hero-"] {{
            background: {p.gradient_secondary}; border-radius: 20px; padding: 28px 30px;
            box-shadow: 0 16px 48px rgba(37,99,235,0.28);
        }}
        div[class*="st-key-about-hero"] {{
            background: {p.gradient_primary}; border-radius: 20px; padding: 28px 30px;
            box-shadow: 0 16px 48px rgba(124,58,237,0.28);
        }}

        .section-title {{ font-size: 1.05rem; font-weight: 600; color: {p.text_primary}; margin: 0 0 2px 0; }}
        .section-subtitle {{ font-size: 0.82rem; color: {p.text_muted}; margin-bottom: 10px; }}

        .page-eyebrow {{
            text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.72rem;
            color: {p.accent_purple}; font-weight: 600; margin-bottom: 2px;
        }}
        .page-title {{ font-size: 1.8rem; font-weight: 800; color: {p.text_primary}; margin: 0; }}
        .page-caption {{ color: {p.text_muted}; font-size: 0.9rem; margin-top: 4px; }}

        .live-pill {{
            display: inline-flex; align-items: center; gap: 6px; background: {p.positive_soft};
            color: {p.positive}; font-size: 0.75rem; font-weight: 600; padding: 4px 10px; border-radius: 20px;
        }}
        .live-dot {{ width: 6px; height: 6px; border-radius: 50%; background: {p.positive}; box-shadow: 0 0 0 3px {p.positive_soft}; }}

        [data-testid="stMetric"] {{ background: transparent; }}
        hr {{ border-color: {p.border}; }}

        /* info (ⓘ) buttons */
        div[class*="st-key-infowrap-"] {{ display: flex; justify-content: flex-end; }}
        div[class*="st-key-infowrap-"] button {{
            width: 24px; height: 24px; min-height: 24px; padding: 0; border-radius: 50%;
            background: transparent; border: 1px solid {p.border}; color: {p.text_muted};
            font-size: 0.72rem; line-height: 1; display: flex; align-items: center; justify-content: center;
            transition: all 0.15s ease;
        }}
        div[class*="st-key-infowrap-"] button:hover {{
            background: {p.table_row_hover}; color: {p.text_primary}; border-color: {p.border_strong};
        }}
        div[class*="st-key-kpi-hero-"] div[class*="st-key-infowrap-"] button,
        div[class*="st-key-forecast-hero-"] div[class*="st-key-infowrap-"] button {{
            border-color: rgba(255,255,255,0.35); color: rgba(255,255,255,0.85);
        }}
        div[class*="st-key-kpi-hero-"] div[class*="st-key-infowrap-"] button:hover,
        div[class*="st-key-forecast-hero-"] div[class*="st-key-infowrap-"] button:hover {{
            background: rgba(255,255,255,0.15); color: white;
        }}

        /* native dialog (info modal) chrome — portal, not under .stApp */
        div[data-testid="stDialog"] div[role="dialog"] {{
            background: {p.surface} !important; color: {p.text_primary} !important;
            border: 1px solid {p.border_strong} !important;
        }}
        div[data-testid="stDialog"] p, div[data-testid="stDialog"] li,
        div[data-testid="stDialog"] span, div[data-testid="stDialog"] div {{ color: {p.text_primary}; }}
        div[data-testid="stDialog"] code {{ background: {p.table_header_bg}; color: {p.text_primary}; }}
        div[data-testid="stDialog"] hr {{ border-color: {p.border}; }}

        /* native form controls (BaseWeb) — text color otherwise stays locked to
           the static server-side theme regardless of our toggle, since these
           are rendered by Streamlit's own widget chrome, not our custom HTML */
        [data-baseweb="select"] > div {{ background: {input_bg} !important; border-color: {p.border} !important; }}
        [data-baseweb="select"] div, [data-baseweb="select"] span, [data-baseweb="select"] input {{
            color: {p.text_primary} !important;
        }}
        [data-baseweb="select"] svg {{ fill: {p.text_muted} !important; }}
        div[data-baseweb="popover"] [data-baseweb="menu"] {{ background: {p.surface} !important; }}
        div[data-baseweb="popover"] li {{ color: {p.text_primary} !important; }}
        [data-baseweb="tag"] {{ background: {p.accent_blue} !important; }}
        [data-baseweb="tag"] span, [data-baseweb="tag"] svg {{ color: white !important; fill: white !important; }}

        /* select_slider (date range) tick labels + selected-value thumbs */
        [data-testid="stSlider"] label {{ color: {p.text_secondary} !important; }}
        [data-testid="stSlider"] [data-testid="stTickBarMin"],
        [data-testid="stSlider"] [data-testid="stTickBarMax"] {{ color: {p.text_muted} !important; }}
        [data-testid="stThumbValue"] {{ color: {p.text_primary} !important; background: {p.surface} !important; }}
        [data-testid="stSliderTrackContainer"] [role="slider"] {{ background: {p.accent_blue} !important; }}

        /* multiselect widget label (collapsed but still present for a11y) + placeholder */
        [data-testid="stMultiSelect"] label {{ color: {p.text_secondary} !important; }}
        div[data-baseweb="popover"] li:hover {{ background: {p.table_row_hover} !important; }}

        /* styled tables (custom HTML — used instead of st.dataframe so both themes are fully controlled) */
        .themed-table-wrap {{ overflow-x: auto; border: 1px solid {p.border}; border-radius: 12px; }}
        table.themed-table {{ width: 100%; border-collapse: collapse; font-size: 0.86rem; }}
        table.themed-table thead th {{
            background: {p.table_header_bg}; color: {p.text_secondary}; text-align: left;
            font-weight: 600; padding: 10px 14px; border-bottom: 1px solid {p.border}; white-space: nowrap;
        }}
        table.themed-table tbody td {{
            padding: 9px 14px; color: {p.text_primary}; border-bottom: 1px solid {p.border}; white-space: nowrap;
        }}
        table.themed-table tbody tr:last-child td {{ border-bottom: none; }}
        table.themed-table tbody tr:hover td {{ background: {p.table_row_hover}; }}
        table.themed-table .best-row td {{ background: {p.positive_soft}; }}

        /* prose sections (About page) */
        .prose p {{ color: {p.text_secondary}; line-height: 1.65; font-size: 0.92rem; margin: 0 0 10px 0; }}
        .prose strong {{ color: {p.text_primary}; }}
        .prose ul {{ margin: 0 0 6px 0; padding-left: 1.1rem; }}
        .prose li {{ color: {p.text_secondary}; line-height: 1.6; font-size: 0.92rem; margin-bottom: 6px; }}
        .prose li strong {{ color: {p.text_primary}; }}

        /* data source cards */
        .source-card {{
            background: {p.table_header_bg}; border: 1px solid {p.border}; border-radius: 12px;
            padding: 14px 16px; height: 100%;
        }}
        .source-card .source-name {{ font-family: monospace; font-weight: 700; color: {p.accent_blue}; font-size: 0.86rem; }}
        .source-card .source-count {{
            float: right; font-size: 0.72rem; font-weight: 600; color: {p.text_muted};
            background: {p.surface}; border: 1px solid {p.border}; border-radius: 20px; padding: 1px 9px;
        }}
        .source-card .source-desc {{ color: {p.text_secondary}; font-size: 0.82rem; margin-top: 8px; line-height: 1.5; clear: both; }}

        /* data flow diagram */
        .flow-row {{ display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; margin: 6px 0; }}
        .flow-box {{
            background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 12px;
            padding: 12px 18px; text-align: center; min-width: 150px;
            font-family: monospace; font-weight: 700; font-size: 0.82rem; color: {p.text_primary};
        }}
        .flow-box.dim {{ border-color: {p.accent_purple}; color: {p.accent_purple}; }}
        .flow-box.core {{
            background: {p.gradient_primary}; color: white; border: none; min-width: 220px; font-size: 0.9rem;
        }}
        .flow-box.fact {{ border-color: {p.accent_cyan}; color: {p.accent_cyan}; }}
        .flow-box .flow-sub {{
            display: block; font-family: 'Inter', sans-serif; font-weight: 400; font-size: 0.72rem;
            color: {p.text_muted}; margin-top: 4px;
        }}
        .flow-box.core .flow-sub {{ color: rgba(255,255,255,0.8); }}
        .flow-arrow {{ text-align: center; font-size: 1.3rem; color: {p.text_muted}; margin: 2px 0; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# --- components --------------------------------------------------------------------

def theme_toggle():
    """Day/Night pill toggle. The button itself IS the pill (styled directly via its
    state-dependent container key) rather than a separate visual overlaid on top of an
    invisible click target — that two-layer approach is what silently broke clicking in
    the browser last time, since the overlay's exact position depends on guessing
    Streamlit's internal DOM, which AppTest can't catch (it doesn't render real CSS).
    Icons use Streamlit's built-in Material Symbols (":material/...:"), not emoji."""
    if "theme_mode" not in st.session_state:
        st.session_state.theme_mode = "dark"
    is_dark = st.session_state.theme_mode == "dark"
    pill_key = "theme-toggle-night" if is_dark else "theme-toggle-day"
    icon = "dark_mode" if is_dark else "light_mode"
    label = "Night" if is_dark else "Day"
    with st.container(key="theme-toggle-wrap"):
        with st.container(key=pill_key):
            clicked = st.button(
                f":material/{icon}: {label}", key="theme-toggle-widget",
                help="Switch between day and night mode",
            )
    if clicked:
        st.session_state.theme_mode = "light" if is_dark else "dark"
        st.rerun()


def sidebar_brand(p: Palette):
    """Branding block pinned to the top of the sidebar — no emoji, left-aligned."""
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:10px; padding: 0 2px 14px 2px;">
            <div style="width:32px; height:32px; border-radius:9px; flex-shrink:0;
                        background: {p.gradient_primary};
                        display:flex; align-items:center; justify-content:center;
                        font-size:0.95rem; font-weight:800; color:white;
                        box-shadow: 0 4px 14px rgba(124,58,237,0.4);">R</div>
            <div style="text-align:left;">
                <div style="font-weight:700; font-size:0.98rem; color:{p.text_primary}; line-height:1.15;">Revenue Forecast</div>
                <div style="font-size:0.7rem; color:{p.text_muted};">SaaS Insights Platform</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_bar():
    """Persistent top-of-main-content bar: MySQL live status, right-aligned."""
    st.markdown(
        "<div class='topbar-status'><span class='live-pill'><span class='live-dot'></span>Live from MySQL</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-bottom: 0.2rem;'></div>", unsafe_allow_html=True)


def nav_rail(current_page: str, pages: list[tuple[str, str, str]]):
    """Emoji icon-only nav rail, fixed top-left of the viewport. Streamlit hides the
    entire sidebar (and everything in it) when the sidebar is collapsed, so this is
    rendered separately in the main content area to keep navigation reachable — CSS
    hides it again whenever the real sidebar is expanded, to avoid a duplicate nav."""
    clicked_slug = None
    with st.container(key="navrail-wrap"):
        for slug, icon, label in pages:
            is_active = current_page == slug
            key = f"navrailitem-active-{slug}" if is_active else f"navrailitem-{slug}"
            with st.container(key=key):
                if st.button(icon, key=f"navrailbtn-{slug}", help=label):
                    clicked_slug = slug
    if clicked_slug:
        st.session_state.page = clicked_slug
        st.rerun()


def page_header(eyebrow: str, title: str, caption: str):
    st.markdown(
        f"""
        <div class="page-eyebrow">{eyebrow}</div>
        <div class="page-title">{title}</div>
        <div class="page-caption">{caption}</div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")


def trend_badge(delta_pct: float | None, good_is_up: bool = True) -> str:
    if delta_pct is None or (isinstance(delta_pct, float) and (delta_pct != delta_pct)):
        return ""
    is_up = delta_pct > 0.05
    is_down = delta_pct < -0.05
    if not is_up and not is_down:
        cls, arrow = "badge-neutral", "→"
    else:
        good = is_up if good_is_up else is_down
        cls = "badge-positive" if good else "badge-negative"
        arrow = "↑" if is_up else "↓"
    return f"<span class='kpi-badge {cls}'>{arrow} {abs(delta_pct):.1f}%</span>"


def kpi_card(
    key: str, label: str, value: str, delta_pct: float | None = None, good_is_up: bool = True,
    sparkline_values=None, sparkline_color: str = "#3b82f6", hero: bool = False,
    visual_id: str | None = None, context: dict | None = None,
):
    container_key = f"kpi-hero-{key}" if hero else f"kpi-{key}"
    with st.container(key=container_key):
        top_col, info_col = st.columns([6, 1])
        with top_col:
            st.markdown(
                f"""
                <div class="kpi-top">
                    <span class="kpi-label">{label}</span>
                    {trend_badge(delta_pct, good_is_up)}
                </div>
                """,
                unsafe_allow_html=True,
            )
        with info_col:
            if visual_id:
                info_button(visual_id, context=context, key=f"info-{key}")
        st.markdown(f"<div class='kpi-value'>{value}</div>", unsafe_allow_html=True)
        if sparkline_values is not None and len(sparkline_values) > 1:
            color = "#ffffff" if hero else sparkline_color
            fig = sparkline_fig(sparkline_values, color)
            st.plotly_chart(fig, width="stretch", config=CHART_CONFIG, key=f"spark-{key}")
        else:
            st.write("")


def panel_start(key: str):
    return st.container(key=f"panel-{key}")


def panel_header(title: str, subtitle: str = "", visual_id: str | None = None, context: dict | None = None, extra=None):
    if visual_id:
        col1, col2 = st.columns([10, 1])
        with col1:
            st.markdown(f"<div class='section-title'>{title}</div>", unsafe_allow_html=True)
            if subtitle:
                st.markdown(f"<div class='section-subtitle'>{subtitle}</div>", unsafe_allow_html=True)
        with col2:
            info_button(visual_id, context=context, extra=extra, key=f"info-{visual_id}")
    else:
        st.markdown(f"<div class='section-title'>{title}</div>", unsafe_allow_html=True)
        if subtitle:
            st.markdown(f"<div class='section-subtitle'>{subtitle}</div>", unsafe_allow_html=True)


def styled_table(headers: list[str], rows: list[list[str]], best_row_index: int | None = None) -> str:
    """Small HTML table matching the current palette — used instead of
    st.dataframe, whose canvas-rendered grid can't be restyled via CSS and
    would otherwise stay locked to the static config.toml theme."""
    head_html = "".join(f"<th>{h}</th>" for h in headers)
    body_html = ""
    for i, row in enumerate(rows):
        cls = " class='best-row'" if i == best_row_index else ""
        cells = "".join(f"<td>{c}</td>" for c in row)
        body_html += f"<tr{cls}>{cells}</tr>"
    return (
        "<div class='themed-table-wrap'><table class='themed-table'>"
        f"<thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table></div>"
    )
