"""
Customer-level monthly status derived from fact_subscription.

A customer can hold multiple concurrent subscriptions (multi-product
upsell), so "churned" here means the customer has *no* active subscription
left as of that month (full logo loss) — not merely that one of several
subscriptions ended. Of the 15 customers with at least one churned
subscription, only 7 are fully gone; the other 8 just downsized products.

Shared by process_data.py (monthly_revenue_summary) and
feature_engineering.py (ml_feature_table) so the definition stays
consistent in one place.
"""

from __future__ import annotations

import pandas as pd


def monthly_customer_status(subscriptions: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    sub = subscriptions.copy()
    sub["start_date"] = pd.to_datetime(sub["start_date"])
    sub["end_date"] = pd.to_datetime(sub["end_date"])

    first_start = sub.groupby("customer_id")["start_date"].min()

    per_customer = sub.groupby("customer_id")["end_date"].agg(
        has_open=lambda s: s.isna().any(), last_end="max"
    )
    fully_churned = per_customer[~per_customer["has_open"]]
    churn_month_by_customer = fully_churned["last_end"].dt.to_period("M").dt.to_timestamp()

    rows = []
    for month in months:
        month_start = month
        month_end = month + pd.offsets.MonthEnd(0)

        overlapping = sub[
            (sub["start_date"] <= month_end)
            & (sub["end_date"].isna() | (sub["end_date"] >= month_start))
        ]
        active_customers = overlapping["customer_id"].nunique()
        new_customers = int(first_start.between(month_start, month_end).sum())
        churned_customers = int((churn_month_by_customer == month_start).sum())

        rows.append({
            "month": month_start, "active_customers": active_customers,
            "new_customers": new_customers, "churned_customers": churned_customers,
        })

    return pd.DataFrame(rows)


def fully_churned_customer_count(subscriptions: pd.DataFrame) -> int:
    """Total customers with no remaining active subscription, as of now —
    the all-time version of monthly_customer_status()'s churned_customers,
    used by the About page's dataset overview."""
    sub = subscriptions.copy()
    sub["end_date"] = pd.to_datetime(sub["end_date"])
    per_customer = sub.groupby("customer_id")["end_date"].agg(has_open=lambda s: s.isna().any())
    return int((~per_customer["has_open"]).sum())
