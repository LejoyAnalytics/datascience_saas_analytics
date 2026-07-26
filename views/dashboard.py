"""Dashboard page — actual/historical data only. No forecast numbers here."""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data_access import (  # noqa: E402
    DataUnavailableError, apply_filters, filter_options, kpi_summary,
    load_dashboard_frames, monthly_series, revenue_by_product, revenue_by_segment,
)
from theme import CHART_CONFIG, area_trace, chart_layout, get_palette, kpi_card, page_header, panel_header, panel_start  # noqa: E402


def pct_change(series: pd.Series) -> float | None:
    if len(series) < 2:
        return None
    prev, last = series.iloc[-2], series.iloc[-1]
    if prev == 0:
        return None
    return float((last - prev) / abs(prev) * 100)


def render():
    palette = get_palette()

    page_header("Analytics", "Dashboard", "Current business situation from actual historical data — no predictions here.")

    try:
        with st.spinner("Loading data from MySQL..."):
            customers, plans, subscriptions, revenue, churn = load_dashboard_frames()
    except DataUnavailableError as e:
        st.error(f"Couldn't load dashboard data. {e}")
        st.stop()

    opts = filter_options(customers, plans, revenue)

    # --- filter bar --------------------------------------------------------------

    with panel_start("filters"):
        panel_header("Filters")
        months_available = pd.date_range(opts["min_month"], opts["max_month"], freq="MS")
        month_labels = [m.strftime("%Y-%m") for m in months_available]

        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        with c1:
            if len(month_labels) > 1:
                start_label, end_label = st.select_slider(
                    "Date range", options=month_labels, value=(month_labels[0], month_labels[-1]),
                    label_visibility="collapsed",
                )
            else:
                start_label = end_label = month_labels[0]
        with c2:
            segments = st.multiselect("Customer segment", opts["segments"], placeholder="All segments", label_visibility="collapsed")
        with c3:
            regions = st.multiselect("Region", opts["regions"], placeholder="All regions", label_visibility="collapsed")
        with c4:
            product_families = st.multiselect("Product / plan", opts["product_families"], placeholder="All products", label_visibility="collapsed")

    start_month, end_month = pd.Timestamp(start_label + "-01"), pd.Timestamp(end_label + "-01")

    filtered = apply_filters(
        customers, plans, subscriptions, revenue, churn,
        start_month, end_month, segments, regions, product_families,
    )

    # live filter context, shown in every info panel on this page
    ctx = {
        "Date range": f"{start_month:%b %Y} – {end_month:%b %Y}",
        "Customer segment": ", ".join(segments) if segments else "All segments",
        "Region": ", ".join(regions) if regions else "All regions",
        "Product / plan": ", ".join(product_families) if product_families else "All products",
    }

    st.write("")

    if filtered["revenue"].empty and filtered["subscriptions"].empty:
        st.info("No data matches the selected filters. Try widening the date range or clearing a filter.")
        return

    series = monthly_series(filtered, start_month, end_month)
    kpis = kpi_summary(filtered, series)

    # --- KPI cards -----------------------------------------------------------------

    row1 = st.columns(4)
    with row1[0]:
        kpi_card("revenue", "Total Revenue", f"${kpis['total_revenue']:,.0f}",
                  pct_change(series["total_revenue"]), True, series["total_revenue"], hero=True,
                  visual_id="kpi-total-revenue", context=ctx)
    with row1[1]:
        kpi_card("mrr", "Current MRR", f"${kpis['current_mrr']:,.0f}",
                  pct_change(series["mrr"]), True, series["mrr"], palette.accent_blue,
                  visual_id="kpi-mrr", context=ctx)
    with row1[2]:
        kpi_card("arr", "Current ARR", f"${kpis['current_arr']:,.0f}",
                  pct_change(series["arr"]), True, series["arr"], palette.accent_cyan,
                  visual_id="kpi-arr", context=ctx)
    with row1[3]:
        kpi_card("active", "Active Customers", f"{kpis['active_customers']:,}",
                  pct_change(series["active_customers"]), True, series["active_customers"], palette.accent_purple,
                  visual_id="kpi-active-customers", context=ctx)

    st.write("")
    row2 = st.columns(3)
    with row2[0]:
        kpi_card("new-cust", "New Customers", f"{kpis['new_customers']:,}",
                  pct_change(series["new_customers"]), True, series["new_customers"], palette.positive,
                  visual_id="kpi-new-customers", context=ctx)
    with row2[1]:
        kpi_card("churned-cust", "Churned Customers", f"{kpis['churned_customers']:,}",
                  pct_change(series["churned_customers"]), False, series["churned_customers"], palette.warning,
                  visual_id="kpi-churned-customers", context=ctx)
    with row2[2]:
        kpi_card("churned-rev", "Churned Revenue (MRR lost)", f"${kpis['churned_revenue']:,.0f}",
                  pct_change(series["churned_revenue"]), False, series["churned_revenue"], palette.negative,
                  visual_id="kpi-churned-revenue", context=ctx)

    st.write("")
    st.write("")

    # --- primary chart: revenue trend ------------------------------------------------

    with panel_start("revenue-trend"):
        panel_header("Revenue trend", "Total recognized revenue by month, for the selected filters",
                      visual_id="chart-revenue-trend", context=ctx)
        fig = go.Figure(area_trace(series["month"], series["total_revenue"], palette.accent_purple, "Revenue"))
        st.plotly_chart(chart_layout(fig, palette, "Revenue ($)", height=380, show_legend=False),
                         width="stretch", config=CHART_CONFIG)

    st.write("")

    # --- charts grid ------------------------------------------------------------------

    col1, col2 = st.columns(2)
    with col1:
        with panel_start("mrr-trend"):
            panel_header("MRR trend", visual_id="chart-mrr-trend", context=ctx)
            fig = go.Figure(area_trace(series["month"], series["mrr"], palette.accent_blue, "MRR"))
            st.plotly_chart(chart_layout(fig, palette, "MRR ($)", show_legend=False), width="stretch", config=CHART_CONFIG)

    with col2:
        with panel_start("active-trend"):
            panel_header("Active customers over time", visual_id="chart-active-trend", context=ctx)
            fig = go.Figure(area_trace(series["month"], series["active_customers"], palette.accent_cyan, "Active customers"))
            st.plotly_chart(chart_layout(fig, palette, "Customers", show_legend=False), width="stretch", config=CHART_CONFIG)

    col3, col4 = st.columns(2)
    with col3:
        with panel_start("new-vs-churned"):
            panel_header("New vs. churned customers", visual_id="chart-new-vs-churned", context=ctx)
            fig = go.Figure()
            fig.add_bar(x=series["month"], y=series["new_customers"], name="New", marker_color=palette.positive)
            fig.add_bar(x=series["month"], y=series["churned_customers"], name="Churned", marker_color=palette.negative)
            fig.update_layout(barmode="group", bargap=0.3)
            st.plotly_chart(chart_layout(fig, palette, "Customers"), width="stretch", config=CHART_CONFIG)

    with col4:
        with panel_start("revenue-by-type"):
            panel_header("Revenue by type", visual_id="chart-revenue-by-type", context=ctx)
            fig = go.Figure()
            for col, name, color in [
                ("renewal", "Renewal", palette.accent_blue),
                ("expansion", "Expansion", palette.accent_cyan),
                ("new", "New", palette.accent_purple),
            ]:
                if col in series.columns:
                    fig.add_bar(x=series["month"], y=series[col], name=name, marker_color=color)
            fig.update_layout(barmode="stack", bargap=0.3)
            st.plotly_chart(chart_layout(fig, palette, "Revenue ($)"), width="stretch", config=CHART_CONFIG)

    col5, col6 = st.columns(2)
    with col5:
        with panel_start("revenue-by-segment"):
            panel_header("Revenue by customer segment", visual_id="chart-revenue-by-segment", context=ctx)
            seg_df = revenue_by_segment(filtered)
            fig = go.Figure(go.Bar(
                x=seg_df["segment"], y=seg_df["net_revenue"],
                marker_color=palette.chart_categorical[: len(seg_df)] if len(seg_df) else None,
            ))
            st.plotly_chart(chart_layout(fig, palette, "Revenue ($)", show_legend=False), width="stretch", config=CHART_CONFIG)

    with col6:
        with panel_start("revenue-by-product"):
            panel_header("Revenue by product", visual_id="chart-revenue-by-product", context=ctx)
            prod_df = revenue_by_product(filtered)
            fig = go.Figure(go.Bar(
                x=prod_df["product_family"], y=prod_df["net_revenue"],
                marker_color=palette.chart_categorical[: len(prod_df)] if len(prod_df) else None,
            ))
            st.plotly_chart(chart_layout(fig, palette, "Revenue ($)", show_legend=False), width="stretch", config=CHART_CONFIG)
