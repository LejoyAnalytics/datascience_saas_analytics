"""
Phase 4: evaluate every candidate model via walk-forward backtesting on
ml_feature_table (MySQL), score with MAE/RMSE/MAPE, pick the best model,
and write model_evaluation_metrics back to MySQL.

Run: python src/evaluate_model.py
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from db import get_engine
from db_writer import write_table
from train_model import MODELS, TEST_MONTHS, walk_forward_backtest


def mae(actual, predicted) -> float:
    return float(np.mean(np.abs(actual - predicted)))


def rmse(actual, predicted) -> float:
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def mape(actual, predicted) -> float:
    return float(np.mean(np.abs((actual - predicted) / actual)) * 100)


def evaluate_all_models(mm: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    backtests = {name: walk_forward_backtest(mm, name) for name in MODELS}
    rows = []
    for name, bt in backtests.items():
        rows.append({
            "model_name": name,
            "mae": mae(bt["actual"], bt["predicted"]),
            "rmse": rmse(bt["actual"], bt["predicted"]),
            "mape": mape(bt["actual"], bt["predicted"]),
        })
    leaderboard = pd.DataFrame(rows).sort_values("mape").reset_index(drop=True)
    return leaderboard, backtests


def main():
    engine = get_engine()
    mm = pd.read_sql("SELECT * FROM ml_feature_table ORDER BY month", engine, parse_dates=["month"])

    min_train = len(mm) - TEST_MONTHS
    assert min_train >= 18, "not enough history for a 12-month walk-forward backtest"

    leaderboard, backtests = evaluate_all_models(mm)

    backtest_start = mm["month"].iloc[-TEST_MONTHS].date()
    backtest_end = mm["month"].iloc[-1].date()

    leaderboard["model_version"] = "v1"
    leaderboard["backtest_start"] = backtest_start
    leaderboard["backtest_end"] = backtest_end
    leaderboard["is_best"] = leaderboard.index == 0
    leaderboard["evaluated_at"] = dt.datetime.now()

    print(f"Walk-forward backtest: {TEST_MONTHS} folds, {backtest_start} to {backtest_end}\n")
    print(leaderboard[["model_name", "mae", "rmse", "mape", "is_best"]].round(2).to_string(index=False))

    n = write_table(leaderboard, "model_evaluation_metrics", engine)
    print(f"\nWrote model_evaluation_metrics: {n} rows")

    best_model = leaderboard.loc[leaderboard["is_best"], "model_name"].iloc[0]
    print(f"Best model: {best_model} (MAPE {leaderboard.loc[leaderboard['is_best'], 'mape'].iloc[0]:.2f}%)")

    engine.dispose()
    return best_model, backtests


if __name__ == "__main__":
    main()
