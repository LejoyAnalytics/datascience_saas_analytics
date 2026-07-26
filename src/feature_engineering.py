"""
Phase 3: build the leak-free ML feature table from monthly_revenue_summary
(MySQL) and write it back to MySQL as ml_feature_table.

Leakage discipline: monthly_revenue_summary is a *descriptive* table — every
column (mrr, active_customers, win_rate, ...) is measured *during* month t,
so a model forecasting month t can't see them yet. Two kinds of predictors
are safe to use as-is:
  - revenue_lag_* / revenue_rolling_* : built with .shift(1), already only
    look at history strictly before t
  - calendar_month / time_index        : known in advance regardless of t

Everything else gets an explicit `_prev` suffix and a one-month shift before
being used as a predictor for total_revenue at month t.

Run: python src/feature_engineering.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from db import get_engine
from db_writer import write_table

LAGS = [1, 2, 3, 6, 12]
ROLLING_WINDOWS = [3, 6, 12]


def build_feature_table(summary: pd.DataFrame) -> pd.DataFrame:
    df = summary.sort_values("month").reset_index(drop=True)
    out = df[["month", "total_revenue"]].copy()

    for lag in LAGS:
        out[f"revenue_lag_{lag}"] = df["total_revenue"].shift(lag)
    for window in ROLLING_WINDOWS:
        out[f"revenue_rolling_mean_{window}"] = df["total_revenue"].shift(1).rolling(window).mean()
        out[f"revenue_rolling_std_{window}"] = df["total_revenue"].shift(1).rolling(window).std()

    # growth as of t uses total_revenue[t] itself -> compute then shift by 1
    out["revenue_growth_mom_prev"] = df["total_revenue"].pct_change().shift(1)
    out["revenue_growth_yoy_prev"] = df["total_revenue"].pct_change(12).shift(1)

    contemporaneous_cols = [c for c in df.columns if c not in ("month", "total_revenue")]
    for col in contemporaneous_cols:
        out[f"{col}_prev"] = df[col].shift(1)

    out["churn_rate_prev"] = (df["churned_customers"] / df["active_customers"].shift(1)).shift(1)

    out["calendar_month"] = df["month"].dt.month
    out["time_index"] = np.arange(len(df))

    return out


def main():
    engine = get_engine()
    summary = pd.read_sql("SELECT * FROM monthly_revenue_summary ORDER BY month", engine, parse_dates=["month"])

    features = build_feature_table(summary)
    n = write_table(features, "ml_feature_table", engine)

    print(f"Wrote ml_feature_table: {n} rows x {features.shape[1]} cols\n")

    null_counts = features.isna().sum()
    print("Null counts (expected: lag/rolling/growth warm-up + win_rate in no-close months):")
    print(null_counts[null_counts > 0].to_string())

    # leakage smell test: no predictor should correlate ~1.0 with the target
    # (a real leak would show up as a near-perfect correlation)
    numeric = features.drop(columns=["month"]).select_dtypes("number")
    corr = numeric.corr()["total_revenue"].drop("total_revenue").abs().sort_values(ascending=False)
    print("\nTop 5 |correlation| with target (sanity check — none should be ~1.0):")
    print(corr.head(5).round(3).to_string())

    engine.dispose()


if __name__ == "__main__":
    main()
