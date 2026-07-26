"""
Phase 5: generate future revenue forecasts with prediction intervals using
the best model from evaluate_model.py, and write every Phase-5 output table
to MySQL:
    model_evaluation_metrics   (re-written here too, so a single run refreshes everything)
    historical_vs_predicted    - best model's backtest: actual vs predicted per month
    revenue_forecast           - future months: point forecast + 80% interval
    forecast_drivers           - the business metrics behind the forecast

Prediction intervals: derived from the best model's walk-forward backtest
residuals (empirical, not a distributional assumption), widened by sqrt(h)
for step h to reflect growing uncertainty further into the future — the
standard random-walk scaling for compounding one-step errors.

Run: python src/forecast.py
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
from scipy.stats import norm

from db import get_engine
from db_writer import write_table
from evaluate_model import evaluate_all_models
from train_model import fit_and_forecast_future

FORECAST_HORIZON = 6
CONFIDENCE_LEVEL = 0.80
MODEL_VERSION = "v1"


def compute_forecast_drivers(summary: pd.DataFrame, lookback: int = 3) -> pd.DataFrame:
    df = summary.sort_values("month").reset_index(drop=True)
    latest = df.iloc[-1]
    prior = df.iloc[-1 - lookback]

    def pct_change(new, old):
        return float((new - old) / old * 100) if old else np.nan

    drivers = [
        ("MRR", latest["mrr"], prior["mrr"]),
        ("ARR", latest["arr"], prior["arr"]),
        ("Active customers", latest["active_customers"], prior["active_customers"]),
        ("Expansion revenue", latest["expansion_revenue"], prior["expansion_revenue"]),
        ("Churn revenue (MRR lost)", latest["churn_revenue"], prior["churn_revenue"]),
        ("Avg. active users", latest["avg_active_users"], prior["avg_active_users"]),
        ("Pipeline weighted value", latest["pipeline_weighted_value"], prior["pipeline_weighted_value"]),
        ("Win rate", latest["win_rate"], prior["win_rate"]),
    ]

    rows = []
    for name, new_val, old_val in drivers:
        change = pct_change(new_val, old_val)
        if pd.isna(change):
            direction = "n/a"
        elif change > 1:
            direction = "up"
        elif change < -1:
            direction = "down"
        else:
            direction = "flat"
        rows.append({
            "driver_name": name, "current_value": float(new_val), "prior_value": float(old_val),
            "pct_change": change, "direction": direction,
            "as_of_month": latest["month"], "lookback_months": lookback,
        })
    return pd.DataFrame(rows)


def build_revenue_forecast(mm: pd.DataFrame, best_model: str, residual_std: float) -> pd.DataFrame:
    point_forecasts = fit_and_forecast_future(mm, best_model, FORECAST_HORIZON)

    last_month = mm["month"].iloc[-1]
    forecast_months = pd.date_range(last_month + pd.DateOffset(months=1), periods=FORECAST_HORIZON, freq="MS")

    z = norm.ppf(0.5 + CONFIDENCE_LEVEL / 2)
    steps = np.arange(1, FORECAST_HORIZON + 1)
    half_widths = z * residual_std * np.sqrt(steps)

    last_actual = mm["total_revenue"].iloc[-1]
    prev_values = np.concatenate([[last_actual], point_forecasts[:-1]])
    growth = (point_forecasts - prev_values) / prev_values * 100

    return pd.DataFrame({
        "forecast_month": forecast_months,
        "predicted_revenue": point_forecasts,
        "lower_bound": point_forecasts - half_widths,
        "upper_bound": point_forecasts + half_widths,
        "forecast_growth": growth,
        "model_name": best_model,
        "model_version": MODEL_VERSION,
        "created_at": dt.datetime.now(),
    })


def main():
    engine = get_engine()
    mm = pd.read_sql("SELECT * FROM ml_feature_table ORDER BY month", engine, parse_dates=["month"])
    summary = pd.read_sql("SELECT * FROM monthly_revenue_summary ORDER BY month", engine, parse_dates=["month"])

    leaderboard, backtests = evaluate_all_models(mm)
    leaderboard["model_version"] = MODEL_VERSION
    leaderboard["backtest_start"] = mm["month"].iloc[-12].date()
    leaderboard["backtest_end"] = mm["month"].iloc[-1].date()
    leaderboard["is_best"] = leaderboard.index == leaderboard["mape"].idxmin()
    leaderboard["evaluated_at"] = dt.datetime.now()
    write_table(leaderboard, "model_evaluation_metrics", engine)

    best_model = leaderboard.loc[leaderboard["is_best"], "model_name"].iloc[0]
    best_bt = backtests[best_model]
    residual_std = float((best_bt["actual"] - best_bt["predicted"]).std(ddof=1))

    hist_vs_pred = best_bt.rename(columns={"actual": "actual_revenue", "predicted": "predicted_revenue"})
    hist_vs_pred["model_name"] = best_model
    hist_vs_pred["model_version"] = MODEL_VERSION
    write_table(hist_vs_pred, "historical_vs_predicted", engine)

    revenue_forecast = build_revenue_forecast(mm, best_model, residual_std)
    write_table(revenue_forecast, "revenue_forecast", engine)

    drivers = compute_forecast_drivers(summary)
    write_table(drivers, "forecast_drivers", engine)

    print(f"Best model: {best_model} (MAPE {leaderboard.loc[leaderboard['is_best'], 'mape'].iloc[0]:.2f}%)")
    print(f"Backtest residual std: ${residual_std:,.2f}  ({CONFIDENCE_LEVEL:.0%} interval)\n")
    print(f"--- {FORECAST_HORIZON}-month forecast ---")
    pd.set_option("display.width", 160)
    print(revenue_forecast[["forecast_month", "predicted_revenue", "lower_bound", "upper_bound", "forecast_growth"]]
          .round(2).to_string(index=False))
    print("\n--- forecast drivers ---")
    print(drivers[["driver_name", "current_value", "prior_value", "pct_change", "direction"]].round(2).to_string(index=False))

    engine.dispose()


if __name__ == "__main__":
    main()
