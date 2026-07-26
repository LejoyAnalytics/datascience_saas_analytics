"""
Backend data-access layer for the dashboard: MySQL -> pandas, with filtering
and aggregation. Every UI page calls into this module rather than touching
SQLAlchemy/pandas directly, so the presentation layer (views/*.py) stays thin.

Read-only against the existing processed tables (dim_customer, dim_product_plan,
fact_subscription, fact_revenue, fact_churn) — no pipeline, schema, or model
code is touched. customer_status.monthly_customer_status is reused as-is from
the pipeline so "active/new/churned" means the same thing everywhere in the app.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from customer_status import monthly_customer_status
from db import get_engine

RAW_FACT_TABLES = [
    "dim_customer", "dim_product_plan", "fact_subscription", "fact_revenue",
    "fact_customer_usage", "fact_churn", "fact_sales_pipeline", "fact_support_ticket",
]

MonthEnd = pd.offsets.MonthEnd


def month_floor(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.to_period("M").dt.to_timestamp()


class DataUnavailableError(Exception):
    """Raised when MySQL can't be reached or a required table is empty/missing."""


# --- raw loads (cached) -------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def load_dashboard_frames():
    try:
        engine = get_engine()
        customers = pd.read_sql(
            "SELECT customer_id, customer_name, industry, region, segment, acquisition_date FROM dim_customer",
            engine, parse_dates=["acquisition_date"],
        )
        plans = pd.read_sql(
            "SELECT plan_id, product_id, product_family, plan_name, plan_tier_name, plan_tier_order, "
            "billing_frequency, price FROM dim_product_plan",
            engine,
        )
        subscriptions = pd.read_sql(
            "SELECT subscription_id, customer_id, plan_id, start_date, end_date, renewal_date, status, mrr, arr "
            "FROM fact_subscription",
            engine, parse_dates=["start_date", "end_date", "renewal_date"],
        )
        revenue = pd.read_sql(
            "SELECT revenue_id, customer_id, subscription_id, revenue_date, gross_revenue, discount, refund, "
            "net_revenue, revenue_type FROM fact_revenue",
            engine, parse_dates=["revenue_date"],
        )
        churn = pd.read_sql(
            "SELECT customer_id, subscription_id, churn_date, churn_reason, mrr_lost FROM fact_churn",
            engine, parse_dates=["churn_date"],
        )
        engine.dispose()
    except Exception as e:
        raise DataUnavailableError(f"Could not load data from MySQL: {e}") from e

    if customers.empty or revenue.empty:
        raise DataUnavailableError("dim_customer or fact_revenue returned no rows. Has the pipeline been run?")

    return customers, plans, subscriptions, revenue, churn


@st.cache_data(ttl=300, show_spinner=False)
def load_forecast_frames():
    try:
        engine = get_engine()
        summary = pd.read_sql("SELECT * FROM monthly_revenue_summary ORDER BY month", engine, parse_dates=["month"])
        forecast = pd.read_sql("SELECT * FROM revenue_forecast ORDER BY forecast_month", engine, parse_dates=["forecast_month"])
        backtest = pd.read_sql("SELECT * FROM historical_vs_predicted ORDER BY month", engine, parse_dates=["month"])
        metrics = pd.read_sql("SELECT * FROM model_evaluation_metrics ORDER BY mape", engine)
        engine.dispose()
    except Exception as e:
        raise DataUnavailableError(f"Could not load forecast tables from MySQL: {e}") from e

    if forecast.empty or summary.empty:
        raise DataUnavailableError("revenue_forecast or monthly_revenue_summary is empty. Has forecast.py been run?")

    return summary, forecast, backtest, metrics


@st.cache_data(ttl=300, show_spinner=False)
def get_table_row_counts() -> dict[str, int]:
    """Live COUNT(*) per processed table, for the About page's dataset
    overview and data-source cards — read straight from MySQL so these
    numbers can never drift from what's actually in the database."""
    from sqlalchemy import text
    counts = {}
    try:
        engine = get_engine()
        with engine.connect() as conn:
            for table in RAW_FACT_TABLES:
                counts[table] = conn.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar()
        engine.dispose()
    except Exception:
        return {t: 0 for t in RAW_FACT_TABLES}
    return counts


@st.cache_data(ttl=300, show_spinner=False)
def get_ml_feature_columns() -> list[str]:
    """Live column list from ml_feature_table, for the info panel's 'features
    used' section — read directly from the schema so it can never drift from
    what train_model.py actually trains on."""
    try:
        engine = get_engine()
        df = pd.read_sql("SELECT * FROM ml_feature_table LIMIT 1", engine)
        engine.dispose()
    except Exception:
        return []
    return [c for c in df.columns if c not in ("month", "total_revenue")]


def filter_options(customers: pd.DataFrame, plans: pd.DataFrame, revenue: pd.DataFrame) -> dict:
    return {
        "segments": sorted(customers["segment"].dropna().unique().tolist()),
        "regions": sorted(customers["region"].dropna().unique().tolist()),
        "product_families": sorted(plans["product_family"].dropna().unique().tolist()),
        "min_month": month_floor(revenue["revenue_date"]).min(),
        "max_month": month_floor(revenue["revenue_date"]).max(),
    }


# --- filtering -----------------------------------------------------------------

def apply_filters(
    customers: pd.DataFrame, plans: pd.DataFrame, subscriptions: pd.DataFrame,
    revenue: pd.DataFrame, churn: pd.DataFrame,
    start_month: pd.Timestamp, end_month: pd.Timestamp,
    segments: list[str] | None, regions: list[str] | None, product_families: list[str] | None,
) -> dict:
    cust_f = customers
    if segments:
        cust_f = cust_f[cust_f["segment"].isin(segments)]
    if regions:
        cust_f = cust_f[cust_f["region"].isin(regions)]
    allowed_customers = set(cust_f["customer_id"])

    plans_f = plans
    if product_families:
        plans_f = plans_f[plans_f["product_family"].isin(product_families)]
    allowed_plans = set(plans_f["plan_id"])

    subs_f = subscriptions[
        subscriptions["customer_id"].isin(allowed_customers) & subscriptions["plan_id"].isin(allowed_plans)
    ].copy()
    allowed_subs = set(subs_f["subscription_id"])

    range_end = end_month + MonthEnd(0)
    rev_f = revenue[
        revenue["customer_id"].isin(allowed_customers)
        & revenue["subscription_id"].isin(allowed_subs)
        & revenue["revenue_date"].between(start_month, range_end)
    ].copy()

    churn_f = churn[
        churn["customer_id"].isin(allowed_customers)
        & churn["subscription_id"].isin(allowed_subs)
        & churn["churn_date"].between(start_month, range_end)
    ].copy()

    return {
        "customers": cust_f, "plans": plans_f, "subscriptions": subs_f,
        "revenue": rev_f, "churn": churn_f,
    }


# --- aggregation -----------------------------------------------------------------

def _mrr_snapshot(subs_f: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    for m in months:
        month_end = m + MonthEnd(0)
        active = subs_f[
            (subs_f["start_date"] <= month_end)
            & (subs_f["end_date"].isna() | (subs_f["end_date"] >= month_end))
        ]
        rows.append({"month": m, "mrr": active["mrr"].sum()})
    df = pd.DataFrame(rows).set_index("month")
    df["arr"] = df["mrr"] * 12
    return df


def _revenue_category_breakdown(subs_f: pd.DataFrame, rev_f: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    empty = pd.DataFrame({"new": 0.0, "expansion": 0.0, "renewal": 0.0}, index=months)
    if rev_f.empty:
        return empty

    sub_sorted = subs_f.sort_values(["customer_id", "start_date"]).copy()
    sub_sorted["is_first_for_customer"] = ~sub_sorted.duplicated("customer_id", keep="first")

    rev = rev_f.merge(sub_sorted[["subscription_id", "is_first_for_customer"]], on="subscription_id", how="left")
    rev["month"] = month_floor(rev["revenue_date"])
    is_new_sub = rev["revenue_type"] == "New"
    is_first = rev["is_first_for_customer"].fillna(False)
    category = np.select(
        [is_new_sub & is_first, is_new_sub & ~is_first, ~is_new_sub],
        ["new", "expansion", "renewal"], default="unknown",
    )
    rev["category"] = category
    pivot = rev.pivot_table(index="month", columns="category", values="net_revenue", aggfunc="sum", fill_value=0.0)
    return pivot.reindex(months, fill_value=0.0).reindex(columns=["new", "expansion", "renewal"], fill_value=0.0)


def monthly_series(filtered: dict, start_month: pd.Timestamp, end_month: pd.Timestamp) -> pd.DataFrame:
    months = pd.date_range(start_month, end_month, freq="MS")
    subs_f, rev_f, churn_f = filtered["subscriptions"], filtered["revenue"], filtered["churn"]

    revenue_by_month = (
        rev_f.assign(month=month_floor(rev_f["revenue_date"])).groupby("month")["net_revenue"].sum()
        if not rev_f.empty else pd.Series(dtype=float)
    ).reindex(months, fill_value=0.0)

    breakdown = _revenue_category_breakdown(subs_f, rev_f, months)
    mrr_df = _mrr_snapshot(subs_f, months)
    status = monthly_customer_status(subs_f, months).set_index("month") if not subs_f.empty else pd.DataFrame(
        {"active_customers": 0, "new_customers": 0, "churned_customers": 0}, index=months
    )
    churned_revenue = (
        churn_f.assign(month=month_floor(churn_f["churn_date"])).groupby("month")["mrr_lost"].sum()
        if not churn_f.empty else pd.Series(dtype=float)
    ).reindex(months, fill_value=0.0)

    out = pd.DataFrame(index=months)
    out.index.name = "month"
    out["total_revenue"] = revenue_by_month
    out = out.join(breakdown).join(mrr_df).join(status)
    out["churned_revenue"] = churned_revenue
    return out.reset_index()


def kpi_summary(filtered: dict, series: pd.DataFrame) -> dict:
    last = series.iloc[-1] if not series.empty else None
    return {
        "total_revenue": float(series["total_revenue"].sum()) if not series.empty else 0.0,
        "current_mrr": float(last["mrr"]) if last is not None else 0.0,
        "current_arr": float(last["arr"]) if last is not None else 0.0,
        "active_customers": int(last["active_customers"]) if last is not None else 0,
        "new_customers": int(series["new_customers"].sum()) if not series.empty else 0,
        "churned_customers": int(series["churned_customers"].sum()) if not series.empty else 0,
        "churned_revenue": float(filtered["churn"]["mrr_lost"].sum()) if not filtered["churn"].empty else 0.0,
    }


def revenue_by_segment(filtered: dict) -> pd.DataFrame:
    rev_f, cust_f = filtered["revenue"], filtered["customers"]
    if rev_f.empty:
        return pd.DataFrame(columns=["segment", "net_revenue"])
    joined = rev_f.merge(cust_f[["customer_id", "segment"]], on="customer_id", how="left")
    return joined.groupby("segment", as_index=False)["net_revenue"].sum().sort_values("net_revenue", ascending=False)


def revenue_by_product(filtered: dict) -> pd.DataFrame:
    rev_f, subs_f, plans_f = filtered["revenue"], filtered["subscriptions"], filtered["plans"]
    if rev_f.empty:
        return pd.DataFrame(columns=["product_family", "net_revenue"])
    joined = (
        rev_f.merge(subs_f[["subscription_id", "plan_id"]], on="subscription_id", how="left")
        .merge(plans_f[["plan_id", "product_family"]], on="plan_id", how="left")
    )
    return joined.groupby("product_family", as_index=False)["net_revenue"].sum().sort_values("net_revenue", ascending=False)
