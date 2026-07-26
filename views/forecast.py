"""Revenue Forecast page — future predictions only, from the stored forecast tables."""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data_access import DataUnavailableError, get_ml_feature_columns, load_forecast_frames  # noqa: E402
from info_panel import info_button  # noqa: E402
from theme import CHART_CONFIG, chart_layout, get_palette, hex_to_rgba, kpi_card, page_header, panel_header, panel_start, styled_table  # noqa: E402


def render():
    palette = get_palette()

    page_header("Forecasting", "Revenue Forecast", "Future revenue predictions from the stored model output — actuals shown only for context.")

    try:
        with st.spinner("Loading forecast data from MySQL..."):
            summary, forecast, backtest, metrics = load_forecast_frames()
    except DataUnavailableError as e:
        st.error(f"Couldn't load forecast data. {e}")
        st.stop()

    best_row = metrics.loc[metrics["is_best"] == 1].iloc[0] if (metrics["is_best"] == 1).any() else metrics.iloc[0]
    next_forecast = forecast.iloc[0]
    growth = next_forecast["forecast_growth"]

    # live model/backtest context, shown in every info panel on this page
    ctx = {
        "Model": next_forecast["model_name"],
        "Model version": next_forecast["model_version"],
        "Training / testing (backtest) period": f"{best_row['backtest_start']} to {best_row['backtest_end']}",
        "Forecast horizon": f"{len(forecast)} months ({forecast['forecast_month'].min():%b %Y} – {forecast['forecast_month'].max():%b %Y})",
        "MAE": f"${best_row['mae']:,.2f}",
        "RMSE": f"${best_row['rmse']:,.2f}",
        "MAPE": f"{best_row['mape']:.2f}%",
        "Evaluated at": str(best_row["evaluated_at"]),
    }
    feature_cols = get_ml_feature_columns()

    # --- hero forecast card ---------------------------------------------------------

    with st.container(key="forecast-hero-main"):
        col_a, col_b = st.columns([10, 1])
        with col_b:
            info_button("forecast-hero", context=ctx, key="info-forecast-hero")
        with col_a:
            st.markdown(
                f"""
                <div class="page-eyebrow" style="color:rgba(255,255,255,0.85);">
                    Next month forecast · {next_forecast['forecast_month']:%B %Y}
                </div>
                <div style="font-size:2.6rem; font-weight:800; color:white; margin:6px 0 18px 0; line-height:1.1;">
                    ${next_forecast['predicted_revenue']:,.0f}
                </div>
                <div style="display:flex; gap:36px; flex-wrap:wrap;">
                    <div>
                        <div style="color:rgba(255,255,255,0.7); font-size:0.75rem;">Growth vs. last month</div>
                        <div style="color:white; font-weight:700; font-size:1.15rem;">{'+' if growth >= 0 else ''}{growth:.1f}%</div>
                    </div>
                    <div>
                        <div style="color:rgba(255,255,255,0.7); font-size:0.75rem;">80% confidence range</div>
                        <div style="color:white; font-weight:700; font-size:1.15rem;">
                            ${next_forecast['lower_bound']:,.0f} – ${next_forecast['upper_bound']:,.0f}
                        </div>
                    </div>
                    <div>
                        <div style="color:rgba(255,255,255,0.7); font-size:0.75rem;">Model used</div>
                        <div style="color:white; font-weight:700; font-size:1.15rem;">{next_forecast['model_name'].title()}</div>
                    </div>
                    <div>
                        <div style="color:rgba(255,255,255,0.7); font-size:0.75rem;">Forecast horizon</div>
                        <div style="color:white; font-weight:700; font-size:1.15rem;">{len(forecast)} months</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.write("")
    st.write("")

    # --- supporting KPI cards --------------------------------------------------------

    col1, col2, col3 = st.columns(3)
    with col1:
        kpi_card("mae", "Mean Absolute Error", f"${best_row['mae']:,.0f}", None, sparkline_color=palette.accent_blue,
                  visual_id="kpi-mae", context=ctx)
    with col2:
        kpi_card("rmse", "Root Mean Sq. Error", f"${best_row['rmse']:,.0f}", None, sparkline_color=palette.accent_cyan,
                  visual_id="kpi-rmse", context=ctx)
    with col3:
        kpi_card("mape", "MAPE (accuracy)", f"{best_row['mape']:.2f}%", None, sparkline_color=palette.accent_purple,
                  visual_id="kpi-mape", context=ctx)

    st.write("")
    st.write("")

    # --- historical vs forecast chart -----------------------------------------------

    with panel_start("hist-vs-forecast"):
        panel_header(
            "Historical vs. forecasted revenue",
            "Solid line = actual recognized revenue · dashed line = forecast · shaded band = 80% confidence interval",
            visual_id="chart-hist-vs-forecast", context=ctx,
        )

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=summary["month"], y=summary["total_revenue"], name="Actual (historical)",
            line=dict(color=palette.text_primary, width=2.5),
            hovertemplate="%{x|%b %Y}: $%{y:,.0f}<extra>Actual</extra>",
        ))
        fig.add_trace(go.Scatter(
            x=list(forecast["forecast_month"]), y=list(forecast["upper_bound"]),
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=list(forecast["forecast_month"]), y=list(forecast["lower_bound"]),
            fill="tonexty", fillcolor=hex_to_rgba(palette.accent_cyan, 0.16), line=dict(width=0),
            name="80% confidence interval", hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=forecast["forecast_month"], y=forecast["predicted_revenue"], name="Forecast (future)",
            line=dict(color=palette.accent_cyan, width=3, dash="dash"), mode="lines+markers",
            marker=dict(size=6),
            hovertemplate="%{x|%b %Y}: $%{y:,.0f}<extra>Forecast</extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[summary["month"].iloc[-1], forecast["forecast_month"].iloc[0]],
            y=[summary["total_revenue"].iloc[-1], forecast["predicted_revenue"].iloc[0]],
            line=dict(color=palette.accent_cyan, width=3, dash="dash"), showlegend=False, hoverinfo="skip",
        ))
        st.plotly_chart(chart_layout(fig, palette, "Revenue ($)", height=440), width="stretch", config=CHART_CONFIG)

    st.write("")

    # --- model accuracy comparison: full-width, landscape layout ---------------------

    with panel_start("model-accuracy"):
        panel_header(
            "Model accuracy comparison",
            f"Walk-forward backtest, {best_row['backtest_start']} to {best_row['backtest_end']}",
            visual_id="panel-model-accuracy", context=ctx,
            extra=[("Features used by tree models (xgboost / lightgbm)", feature_cols)] if feature_cols else None,
        )
        col_table, col_chart = st.columns([2, 3])
        with col_table:
            display_metrics = metrics[["model_name", "mae", "rmse", "mape"]].round(2).sort_values("mape")
            best_idx = list(display_metrics["model_name"]).index(best_row["model_name"])
            rows = [
                [m, f"${mae:,.0f}", f"${rmse:,.0f}", f"{mape:.2f}%"]
                for m, mae, rmse, mape in display_metrics.itertuples(index=False)
            ]
            st.markdown(styled_table(["Model", "MAE", "RMSE", "MAPE %"], rows, best_row_index=best_idx), unsafe_allow_html=True)
        with col_chart:
            if not backtest.empty:
                st.markdown("<div class='section-title' style='font-size:0.85rem;'>Backtest: actual vs. predicted</div>", unsafe_allow_html=True)
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(x=backtest["month"], y=backtest["actual_revenue"], name="Actual",
                                           line=dict(color=palette.text_primary, width=2)))
                fig2.add_trace(go.Scatter(x=backtest["month"], y=backtest["predicted_revenue"], name="Predicted",
                                           line=dict(color=palette.accent_cyan, width=2, dash="dash")))
                st.plotly_chart(chart_layout(fig2, palette, height=240), width="stretch", config=CHART_CONFIG)

    st.write("")

    # --- monthly forecast table: full-width -------------------------------------------

    with panel_start("monthly-table"):
        panel_header("Monthly forecast", visual_id="table-monthly-forecast", context=ctx)
        rows = [
            [
                f"{r.forecast_month:%b %Y}", f"${r.predicted_revenue:,.0f}", f"${r.lower_bound:,.0f}",
                f"${r.upper_bound:,.0f}", f"{r.forecast_growth:+.2f}%",
            ]
            for r in forecast.itertuples(index=False)
        ]
        st.markdown(
            styled_table(["Month", "Predicted revenue", "Lower bound", "Upper bound", "Growth %"], rows),
            unsafe_allow_html=True,
        )
        st.caption(f"Model: **{next_forecast['model_name']}** (v{next_forecast['model_version']}), "
                   f"generated {pd.Timestamp(next_forecast['created_at']):%Y-%m-%d %H:%M}")
