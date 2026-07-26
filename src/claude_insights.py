"""
Claude explains the forecast; it never computes it.

Everything this module sends to Claude is a number already produced by
forecast.py and stored in MySQL (predictions, intervals, drivers, backtest
accuracy). Claude's only job is to turn those numbers into a plain-language
narrative for a business reader — no arithmetic, no re-forecasting.

Requires ANTHROPIC_API_KEY in the environment (or .env).
"""

from __future__ import annotations

import os

import anthropic
import pandas as pd

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5")

SYSTEM_PROMPT = (
    "You are a SaaS business analyst explaining a revenue forecasting model's "
    "output to a non-technical exec. You are given the model's predictions, "
    "confidence intervals, backtest accuracy, and the underlying business "
    "metrics that moved the forecast. Explain what the numbers mean and why "
    "the forecast looks the way it does. Do not perform any calculations of "
    "your own or invent numbers not present in the data given to you. Keep it "
    "to 3-4 short paragraphs, plain language, no headers, no bullet lists."
)


def _format_context(
    model_name: str, mape: float, mae: float, rmse: float,
    drivers: pd.DataFrame, forecast: pd.DataFrame, recent_history: pd.DataFrame,
) -> str:
    lines = [
        f"Selected model: {model_name}",
        f"Backtest accuracy (last 12 months, one-month-ahead): MAPE {mape:.2f}%, MAE ${mae:,.0f}, RMSE ${rmse:,.0f}",
        "",
        "Forecast (next months):",
    ]
    for _, row in forecast.iterrows():
        lines.append(
            f"  {row['forecast_month'].strftime('%Y-%m')}: "
            f"${row['predicted_revenue']:,.0f} "
            f"(range ${row['lower_bound']:,.0f} - ${row['upper_bound']:,.0f}, "
            f"{row['forecast_growth']:+.1f}% vs. prior month)"
        )

    lines.append("")
    lines.append("Recent actual monthly revenue:")
    for _, row in recent_history.iterrows():
        lines.append(f"  {row['month'].strftime('%Y-%m')}: ${row['total_revenue']:,.0f}")

    lines.append("")
    lines.append("Business drivers behind the forecast (current vs. 3 months prior):")
    for _, row in drivers.iterrows():
        pct = f"{row['pct_change']:+.1f}%" if pd.notna(row["pct_change"]) else "n/a"
        lines.append(
            f"  {row['driver_name']}: {row['current_value']:,.2f} "
            f"(was {row['prior_value']:,.2f}, {pct}, trending {row['direction']})"
        )

    return "\n".join(lines)


def generate_insights(
    model_name: str, mape: float, mae: float, rmse: float,
    drivers: pd.DataFrame, forecast: pd.DataFrame, recent_history: pd.DataFrame,
) -> str:
    client = anthropic.Anthropic()
    context = _format_context(model_name, mape, mae, rmse, drivers, forecast, recent_history)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )

    if response.stop_reason == "refusal":
        return "Claude declined to generate insights for this request."

    return "".join(block.text for block in response.content if block.type == "text")
