"""
Model definitions + walk-forward backtesting engine.

This module is a library: it defines each candidate model as a one-step-ahead
fit/predict function and a walk-forward backtest runner. evaluate_model.py
uses it to score every model; forecast.py uses it to fit the winning model on
full history and roll forward into the future.

Walk-forward backtest = expanding window: for month i in the test window,
fit/derive using only rows < i, predict row i, advance one month, repeat.
This is the time-based split applied repeatedly rather than once, so metrics
reflect 12 independent one-month-ahead forecasts.

Models:
    naive, seasonal_naive, moving_avg_3, drift   - baselines
    holt_linear                                    - classical time series (statsmodels)
    xgboost, lightgbm                               - gradient-boosted trees on
                                                       the leak-free feature columns
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

TEST_MONTHS = 12
TARGET_COL = "total_revenue"


def feature_columns(mm: pd.DataFrame) -> list[str]:
    return [c for c in mm.columns if c not in ("month", TARGET_COL)]


# --- one-step-ahead predict functions: predict row i using only rows < i ----

def predict_naive(mm: pd.DataFrame, i: int, feat_cols=None) -> float:
    return mm[TARGET_COL].iloc[i - 1]


def predict_seasonal_naive(mm: pd.DataFrame, i: int, feat_cols=None) -> float:
    return mm[TARGET_COL].iloc[i - 12]


def predict_moving_avg_3(mm: pd.DataFrame, i: int, feat_cols=None) -> float:
    return mm[TARGET_COL].iloc[i - 3:i].mean()


def predict_drift(mm: pd.DataFrame, i: int, feat_cols=None) -> float:
    history = mm[TARGET_COL].iloc[:i]
    avg_change = history.diff().dropna().mean()
    return mm[TARGET_COL].iloc[i - 1] + avg_change


def predict_holt_linear(mm: pd.DataFrame, i: int, feat_cols=None) -> float:
    from statsmodels.tsa.holtwinters import Holt
    history = mm[TARGET_COL].iloc[:i]
    fit = Holt(history.values, initialization_method="estimated").fit(optimized=True)
    return float(fit.forecast(1)[0])


def _fit_predict_tree(model_cls, mm: pd.DataFrame, i: int, feat_cols: list[str], **kwargs) -> float:
    train = mm.iloc[:i].dropna(subset=feat_cols + [TARGET_COL])
    X_train, y_train = train[feat_cols], train[TARGET_COL]
    X_pred = mm.iloc[[i]][feat_cols]
    model = model_cls(**kwargs)
    model.fit(X_train, y_train)
    return float(model.predict(X_pred)[0])


def predict_xgboost(mm: pd.DataFrame, i: int, feat_cols: list[str]) -> float:
    from xgboost import XGBRegressor
    return _fit_predict_tree(
        XGBRegressor, mm, i, feat_cols,
        n_estimators=200, max_depth=3, learning_rate=0.05,
        subsample=0.9, colsample_bytree=0.9, random_state=42,
    )


def predict_lightgbm(mm: pd.DataFrame, i: int, feat_cols: list[str]) -> float:
    from lightgbm import LGBMRegressor
    return _fit_predict_tree(
        LGBMRegressor, mm, i, feat_cols,
        n_estimators=200, max_depth=3, learning_rate=0.05,
        subsample=0.9, colsample_bytree=0.9, random_state=42, verbosity=-1, min_child_samples=5,
    )


MODELS = {
    "naive": predict_naive,
    "seasonal_naive": predict_seasonal_naive,
    "moving_avg_3": predict_moving_avg_3,
    "drift": predict_drift,
    "holt_linear": predict_holt_linear,
    "xgboost": predict_xgboost,
    "lightgbm": predict_lightgbm,
}


def walk_forward_backtest(mm: pd.DataFrame, model_name: str, test_months: int = TEST_MONTHS) -> pd.DataFrame:
    predict_fn = MODELS[model_name]
    feat_cols = feature_columns(mm)
    n = len(mm)
    start = n - test_months
    rows = []
    for i in range(start, n):
        pred = predict_fn(mm, i, feat_cols)
        rows.append({"month": mm["month"].iloc[i], "actual": mm[TARGET_COL].iloc[i], "predicted": pred})
    return pd.DataFrame(rows)


def fit_and_forecast_future(mm: pd.DataFrame, model_name: str, horizon: int) -> np.ndarray:
    """Fit on ALL available history and forecast `horizon` months ahead.
    Tree models forecast recursively: each predicted month's lag/rolling
    features are rebuilt from the growing series (actuals + prior forecasts)
    before predicting the next one."""
    feat_cols = feature_columns(mm)
    extended = mm.copy()
    forecasts = []

    for step in range(horizon):
        pred = _predict_next(extended, model_name, feat_cols)
        forecasts.append(pred)

        new_row = {"month": extended["month"].iloc[-1] + pd.DateOffset(months=1), TARGET_COL: pred}
        extended = pd.concat([extended, pd.DataFrame([new_row])], ignore_index=True)
        extended = _refresh_lag_features(extended)

    return np.array(forecasts)


def _predict_next(mm: pd.DataFrame, model_name: str, feat_cols: list[str]) -> float:
    i = len(mm)
    predict_fn = MODELS[model_name]
    # append a dummy next-month row so predict_* can index position i
    dummy = {"month": mm["month"].iloc[-1] + pd.DateOffset(months=1), TARGET_COL: np.nan}
    for c in feat_cols:
        dummy[c] = mm[c].iloc[-1] if c in ("calendar_month", "time_index") else np.nan
    extended = pd.concat([mm, pd.DataFrame([dummy])], ignore_index=True)
    return predict_fn(extended, i, feat_cols)


def _refresh_lag_features(mm: pd.DataFrame) -> pd.DataFrame:
    """Recompute revenue_lag_*/revenue_rolling_* columns after appending a
    forecast row, so the next recursive step sees consistent features."""
    df = mm.copy()
    for lag in [1, 2, 3, 6, 12]:
        col = f"revenue_lag_{lag}"
        if col in df.columns:
            df[col] = df[TARGET_COL].shift(lag)
    for window in [3, 6, 12]:
        mean_col, std_col = f"revenue_rolling_mean_{window}", f"revenue_rolling_std_{window}"
        if mean_col in df.columns:
            df[mean_col] = df[TARGET_COL].shift(1).rolling(window).mean()
        if std_col in df.columns:
            df[std_col] = df[TARGET_COL].shift(1).rolling(window).std()
    if "revenue_growth_mom_prev" in df.columns:
        df["revenue_growth_mom_prev"] = df[TARGET_COL].pct_change().shift(1)
    if "revenue_growth_yoy_prev" in df.columns:
        df["revenue_growth_yoy_prev"] = df[TARGET_COL].pct_change(12).shift(1)
    if "time_index" in df.columns:
        df["time_index"] = np.arange(len(df))
    if "calendar_month" in df.columns:
        df["calendar_month"] = df["month"].dt.month
    # all other *_prev columns (customer counts, mrr, usage, pipeline...) have no
    # known future value, so they hold their last observed value forward
    for col in df.columns:
        if col.endswith("_prev") and col not in ("revenue_growth_mom_prev", "revenue_growth_yoy_prev"):
            df[col] = df[col].ffill()
    return df
