"""
Reusable "ⓘ" info button + modal, used on every KPI/chart/table.

InfoButton renders a small circular button; clicking it opens InfoModal (a
st.dialog) populated from src/info_metadata.py's centralized config, plus
whatever live `context` (current filters, current model/metrics) the caller
passes in — so the modal always reflects the actual applied filters/values,
never a stale hardcoded description.
"""

from __future__ import annotations

import streamlit as st

from info_metadata import INFO


def _bullet_list(items) -> None:
    for item in items:
        st.markdown(f"- {item}")


@st.dialog("About this visual", width="large")
def _info_dialog(visual_id: str, context: dict | None, extra: list[tuple[str, object]] | None):
    meta = INFO.get(visual_id)
    if meta is None:
        st.warning(f"No metadata registered yet for `{visual_id}`.")
        return

    st.markdown(f"## {meta['title']}")
    if meta.get("represents"):
        st.markdown(meta["represents"])
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if meta.get("source_tables"):
            st.markdown("**Source table(s)**")
            _bullet_list(meta["source_tables"])
        if meta.get("columns_used"):
            st.markdown("**Columns used**")
            _bullet_list(f"`{c}`" for c in meta["columns_used"])
        if meta.get("aggregation"):
            st.markdown("**Aggregation level**")
            st.markdown(meta["aggregation"])
    with col2:
        if meta.get("filters_applied"):
            st.markdown("**Filters that affect this**")
            _bullet_list(meta["filters_applied"])
        if meta.get("formula"):
            st.markdown("**Calculation / formula**")
            st.code(meta["formula"], language="text")

    if meta.get("assumptions"):
        st.divider()
        st.markdown("**Assumptions & limitations**")
        _bullet_list(meta["assumptions"])

    if context:
        st.divider()
        st.markdown("**Currently applied (live values)**")
        for k, v in context.items():
            st.markdown(f"- **{k}:** {v}")

    if meta.get("is_forecast") and meta.get("interval_logic"):
        st.divider()
        st.markdown("**Prediction interval logic**")
        st.code(meta["interval_logic"], language="text")

    if extra:
        for heading, value in extra:
            st.divider()
            st.markdown(f"**{heading}**")
            if isinstance(value, (list, tuple)):
                if len(value) > 10:
                    with st.expander(f"Show all {len(value)}"):
                        st.markdown(", ".join(f"`{v}`" for v in value))
                else:
                    _bullet_list(f"`{v}`" for v in value)
            else:
                st.markdown(value)

    st.divider()
    st.caption(f"Code reference: `{meta.get('code_ref', 'n/a')}`")


def info_button(visual_id: str, context: dict | None = None, extra: list[tuple[str, object]] | None = None, key: str | None = None):
    """Small ⓘ button. Wrap the call site so it sits next to the visual it explains."""
    btn_key = key or f"infobtn-{visual_id}"
    with st.container(key=f"infowrap-{btn_key}"):
        if st.button("ⓘ", key=btn_key, help="What is this? Source, formula, filters, assumptions."):
            _info_dialog(visual_id, context, extra)
