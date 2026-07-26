"""
SaaS Revenue Analytics — entry point.

Three-page app with a persistent, custom-styled left sidebar (Business
Overview / Dashboard / Revenue Forecast) and a dark/light theme toggle that
applies globally to every page. Navigation is hand-rolled with st.button +
session_state (instead of st.navigation) so the active nav item can get a
full gradient treatment via CSS — Streamlit's built-in page nav doesn't
expose enough styling hooks for that. Each views/*.py module exposes a
render() function; all data access still goes through src/data_access.py,
which is the only code that talks to MySQL. A floating chatbot (Groq-backed,
src/chatbot_ui.py) is rendered on top of every page.

Run: streamlit run app.py
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "views"))

from chatbot_ui import render_floating_chatbot  # noqa: E402
from theme import get_palette, inject_css, nav_rail, sidebar_brand, status_bar, theme_toggle  # noqa: E402

st.set_page_config(
    page_title="SaaS Revenue Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "dark"
if "page" not in st.session_state:
    st.session_state.page = "about"

palette = get_palette()
inject_css(palette)

PAGES = [
    ("about", "💼", "Business Overview"),
    ("dashboard", "📊", "Dashboard"),
    ("forecast", "📈", "Revenue Forecast"),
    ("churn", "🔮", "Churn Prediction"),
    ("anomaly", "🚨", "Anomaly Detection"),
]

with st.sidebar:
    sidebar_brand(palette)

    for slug, _icon, label in PAGES:
        is_active = st.session_state.page == slug
        key = f"navitem-active-{slug}" if is_active else f"navitem-{slug}"
        with st.container(key=key):
            if st.button(label, key=f"navbtn-{slug}", width="stretch"):
                st.session_state.page = slug
                st.rerun()

    theme_toggle()

nav_rail(st.session_state.page, PAGES)
status_bar()

if st.session_state.page == "dashboard":
    import dashboard
    dashboard.render()
elif st.session_state.page == "forecast":
    import forecast
    forecast.render()
elif st.session_state.page == "churn":
    import coming_soon
    coming_soon.render("Churn Prediction", "🔮", "Predict which customers are at risk of churning before it happens.")
elif st.session_state.page == "anomaly":
    import coming_soon
    coming_soon.render("Anomaly Detection", "🚨", "Automatically flag unusual spikes or drops in revenue, usage, and churn metrics.")
else:
    import about
    about.render()

render_floating_chatbot(st.session_state.page)
